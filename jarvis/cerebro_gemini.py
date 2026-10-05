"""Cérebro gratuito do JARVIS: Google Gemini (chave grátis do Google AI Studio).

Mesma interface do `Cerebro` (Claude) em jarvis/brain.py, para a tela e o terminal
funcionarem igual com qualquer um dos dois.

Ver a tela e usar mouse/teclado: o Gemini não tem o "computer use" do Claude, então
aqui são funções próprias (ver_tela, clicar, digitar...) que usam o mesmo `Controle`
de jarvis/tools/controle.py. As coordenadas vêm na escala 0-1000 da última captura,
a convenção que o Gemini usa para apontar coisas em imagens.
"""

from __future__ import annotations

import base64
import threading
from typing import Any, Callable

from jarvis import tools
from jarvis.config import config
from jarvis.memory import memoria
from jarvis.personality import system_prompt
from jarvis.tools.controle import ParadaSolicitada, controle

MAX_PASSOS = 60

_COORD = "Coordenada na escala 0 a 1000 da última captura de ver_tela (0,0 = canto superior esquerdo; 1000,1000 = inferior direito)."

# Funções de tela/mouse/teclado: nome -> (descrição, propriedades, obrigatórios)
FUNCOES_PC: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "ver_tela": (
        "Tira um print da tela do usuário e mostra a imagem para você. Use para responder perguntas sobre a tela "
        "e SEMPRE antes de clicar, e de novo depois de cada etapa para conferir se deu certo.",
        {},
        [],
    ),
    "clicar": (
        "Clica num ponto da tela. Chame ver_tela antes para saber onde clicar.",
        {
            "x": {"type": "number", "description": _COORD},
            "y": {"type": "number", "description": _COORD},
            "botao": {"type": "string", "enum": ["esquerdo", "direito", "meio"], "description": "Padrão: esquerdo."},
            "vezes": {"type": "integer", "description": "1 = clique, 2 = duplo clique. Padrão 1."},
        },
        ["x", "y"],
    ),
    "digitar": (
        "Digita um texto onde o cursor estiver (aceita acentos). Clique no campo antes, se precisar.",
        {"texto": {"type": "string"}},
        ["texto"],
    ),
    "apertar_teclas": (
        "Aperta uma tecla ou atalho, ex.: 'Return', 'ctrl+s', 'alt+Tab', 'super' (tecla Windows), 'ctrl+l'.",
        {"teclas": {"type": "string"}, "repetir": {"type": "integer", "description": "Quantas vezes. Padrão 1."}},
        ["teclas"],
    ),
    "rolar": (
        "Rola a tela (roda do mouse).",
        {
            "direcao": {"type": "string", "enum": ["cima", "baixo", "esquerda", "direita"]},
            "quantidade": {"type": "integer", "description": "Quantos 'cliques' da roda. Padrão 3."},
            "x": {"type": "number", "description": "Opcional. " + _COORD},
            "y": {"type": "number", "description": "Opcional. " + _COORD},
        },
        ["direcao"],
    ),
    "arrastar": (
        "Arrasta com o botão esquerdo de um ponto a outro.",
        {
            "x_inicio": {"type": "number", "description": _COORD},
            "y_inicio": {"type": "number", "description": _COORD},
            "x_fim": {"type": "number", "description": _COORD},
            "y_fim": {"type": "number", "description": _COORD},
        },
        ["x_inicio", "y_inicio", "x_fim", "y_fim"],
    ),
    "mover_mouse": (
        "Move o mouse sem clicar (para passar por cima de um menu, por exemplo).",
        {"x": {"type": "number", "description": _COORD}, "y": {"type": "number", "description": _COORD}},
        ["x", "y"],
    ),
    "esperar": (
        "Espera alguns segundos (por exemplo, uma página carregar).",
        {"segundos": {"type": "number"}},
        ["segundos"],
    ),
}
SOMENTE_LEITURA_PC = {"ver_tela", "esperar"}

FUNCAO_PESQUISA = (
    "pesquisar_na_web",
    "Pesquisa no Google informações atuais (notícias, preços, cotações, clima, resultados, lançamentos, "
    "qualquer fato recente) e devolve um resumo com as fontes.",
    {"pergunta": {"type": "string", "description": "O que pesquisar, em linguagem natural."}},
    ["pergunta"],
)


def _limpar_schema(schema: Any) -> Any:
    """Remove chaves do JSON Schema que a API do Gemini não aceita."""
    if isinstance(schema, dict):
        return {k: _limpar_schema(v) for k, v in schema.items() if k not in ("additionalProperties", "$schema")}
    if isinstance(schema, list):
        return [_limpar_schema(v) for v in schema]
    return schema


class CerebroGemini:
    def __init__(
        self,
        confirmar: Callable[[str], bool],
        cliente: Any = None,
        ao_usar_ferramenta: Callable[[str], None] | None = None,
        ao_progresso: Callable[[str], None] | None = None,
        ao_acao_pc: Callable[[str], None] | None = None,
        controle_pc: Any = None,
    ) -> None:
        from google import genai
        from google.genai import types

        self.types = types
        tools.carregar_todas()
        self.cliente = cliente or genai.Client()
        self.confirmar = confirmar
        self.ao_usar_ferramenta = ao_usar_ferramenta or (lambda nome: None)
        self.ao_progresso = ao_progresso or (lambda texto: None)
        self.ao_acao_pc = ao_acao_pc or (lambda descricao: None)
        self.controle = controle_pc or controle
        self.parada = threading.Event()
        self._pc_autorizado: bool | None = None
        self._pedido_atual = ""
        self._ja_viu_tela = False
        self.historico: list[Any] = []

        declaracoes = []
        for nome in sorted(tools.REGISTRO):
            f = tools.REGISTRO[nome]
            declaracoes.append(self._declarar(nome, f.descricao, f.parametros, f.obrigatorios))
        if config.pesquisa_web:
            declaracoes.append(self._declarar(*FUNCAO_PESQUISA))
        if config.controle_pc:
            for nome, (desc, props, obrig) in FUNCOES_PC.items():
                declaracoes.append(self._declarar(nome, desc, props, obrig))
        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt(),
            tools=[types.Tool(function_declarations=declaracoes)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _declarar(self, nome: str, descricao: str, props: dict[str, Any], obrigatorios: list[str]) -> Any:
        schema: dict[str, Any] = {"type": "object", "properties": _limpar_schema(props)}
        if obrigatorios:
            schema["required"] = obrigatorios
        return self.types.FunctionDeclaration(name=nome, description=descricao, parameters_json_schema=schema)

    # ------------------------------------------------------------------
    @property
    def mensagens(self) -> list[Any]:  # compatibilidade com o Cerebro do Claude
        return self.historico

    def nova_conversa(self) -> None:
        self.historico.clear()

    def parar(self) -> None:
        self.parada.set()
        self.controle.parar = True

    def _mensagem_usuario(self, texto: str) -> Any:
        from jarvis.brain import _agora

        contexto = f"[Agora: {_agora()}]"
        if not self.historico:
            fatos = memoria.fatos()
            if fatos:
                contexto += "\n[O que você lembra sobre o usuário:\n" + "\n".join(f"- {f}" for f in fatos) + "]"
        return self.types.Content(role="user", parts=[self.types.Part.from_text(text=f"{contexto}\n{texto}")])

    def _gerar(self) -> Any:
        return self.cliente.models.generate_content(
            model=config.modelo_gemini, contents=self.historico, config=self._config
        )

    # -- ferramentas ----------------------------------------------------
    def _pesquisar(self, pergunta: str) -> str:
        t = self.types
        resp = self.cliente.models.generate_content(
            model=config.modelo_gemini,
            contents=pergunta,
            config=t.GenerateContentConfig(tools=[t.Tool(google_search=t.GoogleSearch())]),
        )
        return _texto(resp) or "A pesquisa não trouxe resultados."

    def _ponto(self, x: Any, y: Any) -> list[float]:
        """0-1000 da última captura -> pixels da captura (o Controle converte para pixels reais)."""
        if not self._ja_viu_tela:
            self.controle.screenshot()
            self._ja_viu_tela = True
        largura, altura = self.controle.tamanho_captura
        return [max(0.0, min(1000.0, float(x))) / 1000 * (largura - 1), max(0.0, min(1000.0, float(y))) / 1000 * (altura - 1)]

    def _acao_pc(self, nome: str, a: dict[str, Any]) -> tuple[str, list[Any]]:
        """Executa uma função de tela/mouse/teclado. Devolve (texto, partes extras com imagem)."""
        c = self.controle
        if nome == "ver_tela":
            imagem = c.screenshot()[0]["source"]
            self._ja_viu_tela = True
            dados = base64.b64decode(imagem["data"])
            return "Captura da tela anexada logo abaixo.", [self.types.Part.from_bytes(data=dados, mime_type=imagem["media_type"])]
        if nome == "clicar":
            botao = {"direito": "right_click", "meio": "middle_click"}.get(a.get("botao", ""), "left_click")
            vezes = int(a.get("vezes") or 1)
            membro = {2: "double_click", 3: "triple_click"}.get(vezes, botao) if botao == "left_click" else botao
            c.executar(membro, {"coordinate": self._ponto(a["x"], a["y"])})
        elif nome == "digitar":
            c.executar("type", {"text": str(a["texto"])})
        elif nome == "apertar_teclas":
            c.executar("key", {"text": str(a["teclas"]), "repeat": int(a.get("repetir") or 1)})
        elif nome == "rolar":
            direcao = {"cima": "up", "baixo": "down", "esquerda": "left", "direita": "right"}[a["direcao"]]
            entrada: dict[str, Any] = {"scroll_direction": direcao, "scroll_amount": int(a.get("quantidade") or 3)}
            if a.get("x") is not None and a.get("y") is not None:
                entrada["coordinate"] = self._ponto(a["x"], a["y"])
            c.executar("scroll", entrada)
        elif nome == "arrastar":
            c.executar("left_click_drag", {"start_coordinate": self._ponto(a["x_inicio"], a["y_inicio"]),
                                           "coordinate": self._ponto(a["x_fim"], a["y_fim"])})
        elif nome == "mover_mouse":
            c.executar("mouse_move", {"coordinate": self._ponto(a["x"], a["y"])})
        elif nome == "esperar":
            c.executar("wait", {"duration": float(a.get("segundos") or 1)})
        return "OK", []

    def _descrever_pc(self, nome: str, a: dict[str, Any]) -> str:
        if nome == "ver_tela":
            return "olhando a tela"
        if "x" in a and "y" in a:
            return f"{nome.replace('_', ' ')} em {float(a['x']):.0f}, {float(a['y']):.0f}"
        if nome == "digitar":
            t = str(a.get("texto", ""))
            return f"digitando “{t[:40]}{'…' if len(t) > 40 else ''}”"
        if nome == "apertar_teclas":
            return f"tecla {a.get('teclas', '')}"
        return nome.replace("_", " ")

    def _executar(self, chamada: Any) -> tuple[dict[str, Any], list[Any]]:
        """Executa uma chamada de função. Devolve (resposta para o modelo, partes extras)."""
        nome = chamada.name
        args = dict(chamada.args or {})
        if nome in FUNCOES_PC:
            if nome not in SOMENTE_LEITURA_PC:
                if self._pc_autorizado is None:
                    self._pc_autorizado = self.confirmar(
                        f"controlar_mouse_e_teclado(tarefa={self._pedido_atual[:160]!r})"
                    )
                if not self._pc_autorizado:
                    return {"erro": "O usuário NÃO autorizou usar o mouse e o teclado neste pedido. Não tente de novo."}, []
            self.ao_acao_pc(self._descrever_pc(nome, args))
            try:
                texto, extras = self._acao_pc(nome, args)
            except ParadaSolicitada:
                return {"erro": "O usuário pediu para parar."}, []
            except Exception as e:
                return {"erro": f"{type(e).__name__}: {e}"}, []
            return {"resultado": texto}, extras
        if nome == FUNCAO_PESQUISA[0]:
            self.ao_usar_ferramenta(nome)
            try:
                return {"resultado": self._pesquisar(str(args.get("pergunta", "")))}, []
            except Exception as e:
                return {"erro": f"A pesquisa falhou: {e}"}, []
        f = tools.REGISTRO.get(nome)
        if f is None:
            return {"erro": f"Função desconhecida: {nome}"}, []
        if f.risco == tools.CONFIRMAR and not self.confirmar(f.resumo(args)):
            return {"erro": "O usuário NÃO autorizou esta ação. Não a execute por outro meio."}, []
        self.ao_usar_ferramenta(nome)
        try:
            return {"resultado": tools.executar(nome, args) or "Feito."}, []
        except Exception as e:
            return {"erro": f"{type(e).__name__}: {e}"}, []

    # ------------------------------------------------------------------
    def responder(self, texto: str) -> str:
        from google.genai import errors

        t = self.types
        inicio = len(self.historico)
        self.parada.clear()
        self.controle.parar = False
        self._pc_autorizado = None
        self._pedido_atual = texto
        self.historico.append(self._mensagem_usuario(texto))
        try:
            for _ in range(MAX_PASSOS):
                if self.parada.is_set():
                    if len(self.historico) - inicio > 1:
                        self.historico.append(t.Content(role="model", parts=[t.Part.from_text(text="Parei a pedido do usuário.")]))
                    else:
                        del self.historico[inicio:]
                    return "Parei, senhor."
                resp = self._gerar()
                if not resp.candidates or resp.candidates[0].content is None or not resp.candidates[0].content.parts:
                    del self.historico[inicio:]
                    return "Receio que não posso ajudar com isso, senhor."
                conteudo = resp.candidates[0].content
                self.historico.append(conteudo)  # sem alterar: preserva as "thought signatures"
                chamadas = resp.function_calls or []
                if not chamadas:
                    return _texto(resp) or "Feito, senhor."
                nota = _texto(resp)
                if nota:
                    self.ao_progresso(nota)
                partes, extras = [], []
                for chamada in chamadas:
                    resposta, mais = self._executar(chamada)
                    parte = t.Part.from_function_response(name=chamada.name, response=resposta)
                    if getattr(chamada, "id", None):
                        parte.function_response.id = chamada.id
                    partes.append(parte)
                    extras.extend(mais)
                self.historico.append(t.Content(role="user", parts=partes + extras))
            return "Essa tarefa ficou longa demais, senhor. Parei por segurança."
        except errors.APIError as e:
            del self.historico[inicio:]
            return _mensagem_erro(e)
        except Exception as e:  # rede, por exemplo
            del self.historico[inicio:]
            nome = type(e).__name__
            if "Connect" in nome or "Timeout" in nome or "Network" in nome:
                return "Perdi a conexão com meus servidores, senhor. Verifique a internet."
            return f"Tive um problema técnico, senhor ({nome})."


def _texto(resp: Any) -> str:
    """Junta só as partes de texto da resposta (ignora pensamentos e chamadas de função)."""
    try:
        partes = resp.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return ""
    return " ".join(p.text for p in partes if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()


def _mensagem_erro(e: Any) -> str:
    codigo = getattr(e, "code", None)
    msg = str(getattr(e, "message", "") or e)
    if codigo == 429:
        return "Atingi o limite gratuito do Gemini por agora, senhor. Tente de novo em alguns minutos."
    if codigo in (400, 401, 403) and ("API key" in msg or "API_KEY" in msg or codigo in (401, 403)):
        return "Minha chave do Gemini parece inválida, senhor. Rode python -m jarvis --configurar para trocar."
    if codigo == 404:
        return "O modelo do Gemini configurado não existe mais, senhor. Ajuste JARVIS_MODELO_GEMINI no arquivo ponto env."
    if codigo and codigo >= 500:
        return "Os servidores do Gemini estão instáveis agora, senhor. Tente de novo em instantes."
    return f"Tive um problema técnico, senhor (erro {codigo})."
