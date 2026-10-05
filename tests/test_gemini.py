"""Cérebro Gemini testado contra um servidor falso que imita a API do Google."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from google import genai
from google.genai import types

from jarvis import tools
from jarvis.cerebro_gemini import CerebroGemini, _limpar_schema


class ApiFalsa:
    """Responde em sequência; guarda os corpos recebidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        api = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                api.pedidos.append({"path": self.path, **json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
                status, corpo = api.respostas.pop(0)
                dados = json.dumps(corpo).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cliente = genai.Client(
            api_key="teste",
            http_options=types.HttpOptions(base_url=f"http://127.0.0.1:{self.srv.server_address[1]}", retry_options=None),
        )

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


def ok(*partes):
    return 200, {"candidates": [{"content": {"role": "model", "parts": list(partes)}, "finishReason": "STOP"}]}


def chamada(nome, args, id_="c1"):
    return {"functionCall": {"name": nome, "args": args, "id": id_}}


class ControleFalso:
    def __init__(self):
        self.feitas = []
        self.parar = False
        self.tamanho_captura = (1000, 500)

    def screenshot(self):
        self.feitas.append(("screenshot", {}))
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAEC"}}]

    def executar(self, nome, entrada):
        self.feitas.append((nome, entrada))
        return "OK"


@pytest.fixture
def api_falsa():
    criadas = []

    def criar(respostas):
        a = ApiFalsa(respostas)
        criadas.append(a)
        return a

    yield criar
    for a in criadas:
        a.fechar()


def test_resposta_simples(api_falsa):
    api = api_falsa([ok({"text": "Olá, senhor."})])
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    assert c.responder("oi") == "Olá, senhor."
    pedido = api.pedidos[0]
    assert ":generateContent" in pedido["path"]
    assert "J.A.R.V.I.S." in json.dumps(pedido["systemInstruction"], ensure_ascii=False)
    nomes = {f["name"] for f in pedido["tools"][0]["functionDeclarations"]}
    assert {"abrir_programa", "criar_lembrete", "ver_tela", "clicar", "pesquisar_na_web"} <= nomes
    assert "additionalProperties" not in json.dumps(pedido["tools"])


def test_funcao_executada_e_resposta_devolvida(api_falsa):
    feitas = []

    @tools.ferramenta("_g_teste", "teste", {"x": {"type": "string"}}, ["x"])
    def _g(x):
        feitas.append(x)
        return f"ok {x}"

    try:
        api = api_falsa([ok({"text": "Um momento."}, chamada("_g_teste", {"x": "a"})), ok({"text": "Feito."})])
        notas = []
        c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso(), ao_progresso=notas.append)
        assert c.responder("faz") == "Feito."
        assert feitas == ["a"] and notas == ["Um momento."]
        ultimo = api.pedidos[1]["contents"][-1]
        resposta = ultimo["parts"][0]["functionResponse"]
        assert resposta["name"] == "_g_teste" and resposta["id"] == "c1"
        assert resposta["response"] == {"resultado": "ok a"}
        # o turno do modelo volta inalterado no histórico
        assert api.pedidos[1]["contents"][1]["parts"][1]["functionCall"]["name"] == "_g_teste"
    finally:
        tools.REGISTRO.pop("_g_teste")


def test_ver_tela_envia_imagem_e_clique_converte_coordenadas(api_falsa):
    api = api_falsa([
        ok(chamada("ver_tela", {}, "v")),
        ok(chamada("clicar", {"x": 500, "y": 1000}, "k1"), chamada("digitar", {"texto": "olá"}, "k2")),
        ok({"text": "Pronto."}),
    ])
    pc = ControleFalso()
    perguntas = []
    c = CerebroGemini(lambda r: perguntas.append(r) or True, cliente=api.cliente, controle_pc=pc)
    assert c.responder("abre e escreve") == "Pronto."
    partes = api.pedidos[1]["contents"][-1]["parts"]
    assert partes[0]["functionResponse"]["name"] == "ver_tela"
    imagem = partes[1]["inlineData"]
    assert (imagem.get("mimeType") or imagem.get("mime_type")) == "image/jpeg" and imagem["data"] == "AAEC"
    assert pc.feitas[1] == ("left_click", {"coordinate": [499.5, 499.0]})
    assert pc.feitas[2] == ("type", {"text": "olá"})
    assert len(perguntas) == 1 and perguntas[0].startswith("controlar_mouse_e_teclado")


def test_recusa_de_controle(api_falsa):
    api = api_falsa([ok(chamada("clicar", {"x": 1, "y": 1})), ok({"text": "Tudo bem."})])
    pc = ControleFalso()
    CerebroGemini(lambda r: False, cliente=api.cliente, controle_pc=pc).responder("clica")
    assert pc.feitas == []
    assert "NÃO autorizou" in api.pedidos[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["erro"]


def test_limite_gratuito_vira_mensagem_amigavel(api_falsa):
    erro = (429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    api = api_falsa([erro] * 4)  # principal: 2 tentativas; reserva: 2 tentativas
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    c._esperar = lambda s: False
    assert "limite gratuito" in c.responder("oi")
    assert len(api.pedidos) == 4
    assert c.historico == []


def test_chave_invalida(api_falsa):
    api = api_falsa([(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})])
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    assert "chave do Gemini" in c.responder("oi")


def test_parar(api_falsa):
    api = api_falsa([ok(chamada("ver_tela", {}))])
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso(), ao_acao_pc=lambda t: c.parar())
    assert c.responder("faz várias coisas") == "Parei, senhor."
    assert len(api.pedidos) == 1


def test_limpar_schema():
    s = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string", "additionalProperties": 1}}}
    assert _limpar_schema(s) == {"type": "object", "properties": {"a": {"type": "string"}}}


def test_fabrica_escolhe_gemini(monkeypatch):
    from jarvis import brain
    from jarvis.config import config

    monkeypatch.setenv("JARVIS_IA", "")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert config.ia == "gemini" and config.modelo_ativo == config.modelo_gemini
    assert type(brain.criar_cerebro(confirmar=lambda r: True)).__name__ == "CerebroGemini"
    monkeypatch.setenv("JARVIS_IA", "claude")
    assert config.ia == "claude"


def test_configurar_grava_env_sem_perder_comentarios(tmp_path):
    from jarvis.configurar import gravar_env, ler_env

    arq = tmp_path / ".env"
    arq.write_text("# comentário\nJARVIS_NOME_USUARIO=senhor\nJARVIS_VOZ=pt-BR-AntonioNeural\n", encoding="utf-8")
    gravar_env({"JARVIS_NOME_USUARIO": "Gustavo", "GEMINI_API_KEY": "abc"}, arq)
    assert arq.read_text(encoding="utf-8").startswith("# comentário\n")
    assert ler_env(arq) == {"JARVIS_NOME_USUARIO": "Gustavo", "JARVIS_VOZ": "pt-BR-AntonioNeural", "GEMINI_API_KEY": "abc"}
