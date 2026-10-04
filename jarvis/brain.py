"""O cérebro do JARVIS: conversa com o Claude e executa as ferramentas pedidas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import anthropic

from jarvis import tools
from jarvis.config import config
from jarvis.memory import memoria
from jarvis.personality import system_prompt

MAX_PASSOS = 25  # limite de idas e voltas com ferramentas por pedido

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _agora() -> str:
    a = datetime.now().astimezone()
    return f"{_DIAS[a.weekday()]}, {a:%d/%m/%Y %H:%M} (fuso {a:%z})"


class Cerebro:
    def __init__(
        self,
        confirmar: Callable[[str], bool],
        cliente: anthropic.Anthropic | None = None,
        ao_usar_ferramenta: Callable[[str], None] | None = None,
    ) -> None:
        tools.carregar_todas()
        self.cliente = cliente or anthropic.Anthropic()
        self.confirmar = confirmar
        self.ao_usar_ferramenta = ao_usar_ferramenta or (lambda nome: None)
        self.mensagens: list[dict[str, Any]] = []
        self._system = [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
        self._ferramentas: list[dict[str, Any]] = tools.schemas()
        if config.pesquisa_web:
            self._ferramentas.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 5})

    # ------------------------------------------------------------------
    def _chamar_claude(self) -> Any:
        return self.cliente.beta.messages.create(
            model=config.modelo,
            max_tokens=16000,
            system=self._system,
            tools=self._ferramentas,
            messages=self.mensagens,
            thinking={"type": "adaptive"},
            output_config={"effort": config.esforco},
            cache_control={"type": "ephemeral"},  # cacheia o histórico a cada turno
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def _mensagem_usuario(self, texto: str) -> dict[str, Any]:
        contexto = f"[Agora: {_agora()}]"
        if not self.mensagens:  # primeira mensagem da sessão leva as memórias
            fatos = memoria.fatos()
            if fatos:
                contexto += "\n[O que você lembra sobre o usuário:\n" + "\n".join(f"- {f}" for f in fatos) + "]"
        return {"role": "user", "content": f"{contexto}\n{texto}"}

    def _executar_ferramentas(self, blocos: list[Any]) -> list[dict[str, Any]]:
        resultados = []
        for bloco in blocos:
            f = tools.REGISTRO.get(bloco.name)
            entrada = dict(bloco.input or {})
            resultado: dict[str, Any] = {"type": "tool_result", "tool_use_id": bloco.id}
            if f is None:
                resultado |= {"content": f"Ferramenta desconhecida: {bloco.name}", "is_error": True}
            elif f.risco == tools.CONFIRMAR and not self.confirmar(f.resumo(entrada)):
                resultado["content"] = "O usuário NÃO autorizou esta ação. Não a execute por outro meio."
            else:
                self.ao_usar_ferramenta(bloco.name)
                try:
                    resultado["content"] = tools.executar(bloco.name, entrada) or "Feito."
                except Exception as e:  # o erro volta para o Claude explicar/tentar outra coisa
                    resultado |= {"content": f"Erro: {type(e).__name__}: {e}", "is_error": True}
            resultados.append(resultado)
        return resultados

    # ------------------------------------------------------------------
    def responder(self, texto: str) -> str:
        """Processa um pedido do usuário e devolve a resposta final (para falar/mostrar)."""
        inicio_turno = len(self.mensagens)
        self.mensagens.append(self._mensagem_usuario(texto))
        try:
            for _ in range(MAX_PASSOS):
                resp = self._chamar_claude()

                if resp.stop_reason == "refusal":
                    del self.mensagens[inicio_turno:]
                    return "Receio que não posso ajudar com isso, senhor."

                self.mensagens.append({"role": "assistant", "content": resp.content})

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
