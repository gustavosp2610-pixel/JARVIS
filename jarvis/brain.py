"""O cérebro do JARVIS: conversa com o Claude e executa as ferramentas pedidas."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable

import anthropic

from jarvis import tools
from jarvis.config import config
from jarvis.personality import system_prompt
from jarvis.tools.controle import NAO_EXECUTADO, SOMENTE_LEITURA, TOOLSET, ParadaSolicitada, controle

log = logging.getLogger("jarvis")
MAX_PASSOS = 60  # limite de idas e voltas com ferramentas por pedido (tarefas no PC usam muitas)
BETAS = ["server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18"]

def _agora() -> str:
    from jarvis.contexto import agora_texto

    return agora_texto()


class Cerebro:
    def __init__(
        self,
        confirmar: Callable[[str], bool],
        cliente: anthropic.Anthropic | None = None,
        ao_usar_ferramenta: Callable[[str], None] | None = None,
        ao_progresso: Callable[[str], None] | None = None,
        ao_acao_pc: Callable[[str], None] | None = None,
        controle_pc: Any = None,
    ) -> None:
        tools.carregar_todas()
        self.cliente = cliente or anthropic.Anthropic()
        self.confirmar = confirmar
        self.ao_usar_ferramenta = ao_usar_ferramenta or (lambda nome: None)
        self.ao_progresso = ao_progresso or (lambda texto: None)
        self.ao_acao_pc = ao_acao_pc or (lambda descricao: None)
        self.controle = controle_pc or controle
        self.parada = threading.Event()
        self._pc_autorizado: bool | None = None  # None = ainda não perguntado neste pedido
        self._pedido_atual = ""
        self.mensagens: list[dict[str, Any]] = []
        self._system = [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
        self._ferramentas: list[dict[str, Any]] = tools.schemas()
        if config.pesquisa_web:
            self._ferramentas.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 5})
        if config.controle_pc:
            self._ferramentas.append(dict(TOOLSET))

    # ------------------------------------------------------------------
    def _chamar_claude(self) -> Any:
        return self.cliente.beta.messages.create(
            model=config.modelo,
            max_tokens=16000,
            system=self._system,
            tools=self._ferramentas,
            messages=self.mensagens,
            # "updates": notas curtas de progresso entre ferramentas ("Abrindo o navegador...")
            thinking={"type": "adaptive", "display": "updates"},
            output_config={"effort": config.esforco},
            cache_control={"type": "ephemeral"},  # cacheia o histórico a cada turno
            betas=BETAS,
            fallbacks="default",
        )

    def _mensagem_usuario(self, texto: str) -> dict[str, Any]:
        from jarvis.contexto import contexto_usuario

        return {"role": "user", "content": f"{contexto_usuario(not self.mensagens)}\n{texto}"}

    def _autorizar_pc(self) -> bool:
        """Uma autorização por pedido para usar mouse e teclado."""
        if self._pc_autorizado is None:
            self._pc_autorizado = self.confirmar(f"controlar_mouse_e_teclado(tarefa: {self._pedido_atual[:160]})")
        return self._pc_autorizado

    def _executar_pc(self, bloco: Any, falhou: bool) -> tuple[dict[str, Any], bool]:
        resultado: dict[str, Any] = {"type": "tool_result", "tool_use_id": bloco.id, "toolset_name": "computer"}
        if falhou:
            return resultado | {"content": NAO_EXECUTADO, "is_error": True}, True
        entrada = dict(bloco.input or {})
        if bloco.name not in SOMENTE_LEITURA and not self._autorizar_pc():
            msg = "O usuário NÃO autorizou usar o mouse e o teclado neste pedido. Não tente de novo."
            return resultado | {"content": msg, "is_error": True}, True
        self.ao_acao_pc(self.controle.descrever(bloco.name, entrada))
        try:
            saida = self.controle.executar(bloco.name, entrada)
        except ParadaSolicitada:
            return resultado | {"content": "O usuário pediu para parar.", "is_error": True}, True
        except Exception as e:
            return resultado | {"content": f"Erro: {type(e).__name__}: {e}", "is_error": True}, True
        return resultado | {"content": saida if isinstance(saida, list) else str(saida)}, False

    def _executar_ferramentas(self, blocos: list[Any]) -> list[dict[str, Any]]:
        resultados = []
        falhou_pc = False  # num lote de ações no PC, para na primeira falha
        for bloco in blocos:
            if getattr(bloco, "toolset_name", None) == "computer":
                resultado, falhou_pc = self._executar_pc(bloco, falhou_pc)
                resultados.append(resultado)
                continue
            f = tools.REGISTRO.get(bloco.name)
            entrada = dict(bloco.input or {})
            resultado = {"type": "tool_result", "tool_use_id": bloco.id}
            if f is not None:
                try:
                    entrada = tools.preparar(bloco.name, entrada)
                except ValueError as e:
                    resultados.append(resultado | {"content": f"Erro: {e}", "is_error": True})
                    continue
            if f is None:
                resultado |= {"content": f"Ferramenta desconhecida: {bloco.name}", "is_error": True}
            elif f.risco == tools.CONFIRMAR and not self.confirmar(f.resumo(entrada)):
                resultado["content"] = "O usuário NÃO autorizou esta ação. Não a execute por outro meio."
            else:
                self.ao_usar_ferramenta(bloco.name)
                try:
                    resultado["content"] = tools.executar(bloco.name, entrada) or "Feito."
                except tools.FalhaFerramenta as e:
                    log.warning("%s falhou: %s", bloco.name, e)
                    resultado |= {"content": tools.PREFIXO_FALHA + str(e), "is_error": True}
                except Exception as e:  # o erro volta para o Claude explicar/tentar outra coisa
                    log.warning("%s falhou: %s: %s", bloco.name, type(e).__name__, e)
                    resultado |= {"content": f"{tools.PREFIXO_FALHA}{type(e).__name__}: {e}", "is_error": True}
            resultados.append(resultado)
        return resultados

    def parar(self) -> None:
        """Interrompe o pedido em andamento (botão Parar)."""
        self.parada.set()
        self.controle.parar = True

    # ------------------------------------------------------------------
    def responder(self, texto: str) -> str:
        """Processa um pedido do usuário e devolve a resposta final (para falar/mostrar)."""
        inicio_turno = len(self.mensagens)
        self.parada.clear()
        self.controle.parar = False
        self._pc_autorizado = None
        self._pedido_atual = texto
        self.mensagens.append(self._mensagem_usuario(texto))
        try:
            for _ in range(MAX_PASSOS):
                if self.parada.is_set():
                    if self.mensagens[-1]["role"] == "user" and len(self.mensagens) - inicio_turno > 1:
                        self.mensagens.append({"role": "assistant", "content": "Parei a pedido do usuário."})
                    else:
                        del self.mensagens[inicio_turno:]
                    return "Parei, senhor."
                resp = self._chamar_claude()

                if resp.stop_reason == "refusal":
                    del self.mensagens[inicio_turno:]
                    return "Receio que não posso ajudar com isso, senhor."

                self.mensagens.append({"role": "assistant", "content": resp.content})
                for bloco in resp.content:
                    nota = getattr(bloco, "thinking", "") if bloco.type == "thinking" else ""
                    if nota and nota.strip():
                        self.ao_progresso(nota.strip())

                if resp.stop_reason == "pause_turn":  # pesquisa web longa: continuar
                    continue
                if resp.stop_reason == "tool_use":
                    pedidos = [b for b in resp.content if b.type == "tool_use"]
                    self.mensagens.append({"role": "user", "content": self._executar_ferramentas(pedidos)})
                    continue

                texto_final = " ".join(b.text for b in resp.content if b.type == "text").strip()
                return texto_final or "Feito, senhor."
            return "Essa tarefa ficou longa demais, senhor. Parei por segurança."
        except anthropic.AuthenticationError:
            del self.mensagens[inicio_turno:]
            return "Minha chave de acesso ao Claude parece inválida, senhor. Verifique o arquivo ponto env."
        except anthropic.RateLimitError:
            del self.mensagens[inicio_turno:]
            return "Estou recebendo pedidos demais no momento, senhor. Tente de novo em alguns segundos."
        except anthropic.APIConnectionError:
            del self.mensagens[inicio_turno:]
            return "Perdi a conexão com meus servidores, senhor. Verifique a internet."
        except anthropic.APIStatusError as e:
            del self.mensagens[inicio_turno:]
            return f"Tive um problema técnico, senhor (erro {e.status_code})."

    def nova_conversa(self) -> None:
        self.mensagens.clear()


def criar_cerebro(**kwargs: Any) -> Any:
    """Cria o cérebro configurado: Gemini (grátis) ou Claude (pago por uso)."""
    if config.ia == "gemini":
        from jarvis.cerebro_gemini import CerebroGemini

        return CerebroGemini(**kwargs)
    return Cerebro(**kwargs)
