"""Configurador do Gmail, prefixo de falha e troca rápida de modelo quando a cota acaba."""

from types import SimpleNamespace

import pytest

from jarvis import cerebro_gemini, configurar, tools
from jarvis.brain import Cerebro
from jarvis.cerebro_gemini import CerebroGemini
from jarvis.tools import google
from tests.test_gemini import ControleFalso, api_falsa, chamada, ok  # noqa: F401 (fixture)

COTA = (429, {"error": {"code": 429, "message": "You exceeded your current quota, please check your plan.", "status": "RESOURCE_EXHAUSTED"}})


@pytest.fixture(autouse=True)
def limpar_esgotados(monkeypatch):
    # o configurador grava no os.environ; setenv aqui garante que tudo volta ao normal depois
    monkeypatch.setenv("GMAIL_ENDERECO", "")
    monkeypatch.setenv("GMAIL_SENHA_APP", "")
    cerebro_gemini._ESGOTADOS.clear()
    yield
    cerebro_gemini._ESGOTADOS.clear()


def test_cota_esgotada_vai_direto_ao_reserva_e_lembra(api_falsa):  # noqa: F811
    api = api_falsa([COTA, ok({"text": "Do reserva."}), ok({"text": "De novo do reserva."})])
    esperas = []
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    c._esperar = lambda s: esperas.append(s) or False
    assert c.responder("oi") == "Do reserva."
    assert c.responder("e agora?") == "De novo do reserva."
    assert esperas == []  # nada de esperar
    caminhos = [p["path"] for p in api.pedidos]
    assert "flash-lite" not in caminhos[0] and all("flash-lite" in p for p in caminhos[1:])


def test_falha_de_ferramenta_chega_com_prefixo_no_gemini(api_falsa, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.delenv("GMAIL_ENDERECO", raising=False)
    monkeypatch.delenv("GMAIL_SENHA_APP", raising=False)
    monkeypatch.setattr(google, "TOKEN", tmp_path / "x.json")
    api = api_falsa([ok(chamada("enviar_email", {"para": "a@b.com", "assunto": "x", "corpo": "y"})), ok({"text": "Não deu."})])
    CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso()).responder("manda")
    erro = api.pedidos[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["erro"]
    assert erro.startswith("FALHOU — a ação NÃO foi feita") and "conectar_gmail.bat" in erro


def test_falha_de_ferramenta_chega_com_prefixo_no_claude(monkeypatch, tmp_path):
    monkeypatch.delenv("GMAIL_ENDERECO", raising=False)
    monkeypatch.delenv("GMAIL_SENHA_APP", raising=False)
    monkeypatch.setattr(google, "TOKEN", tmp_path / "x.json")
    respostas = [
        ("tool_use", [SimpleNamespace(type="tool_use", name="enviar_email", id="t1", input={"para": "a@b.com", "assunto": "x", "corpo": "y"})]),
        ("end_turn", [SimpleNamespace(type="text", text="Não deu.")]),
    ]
    chamadas = []

    def criar(**kw):
        chamadas.append(list(kw["messages"]))
        stop, conteudo = respostas.pop(0)
        return SimpleNamespace(stop_reason=stop, content=conteudo)

    Cerebro(lambda r: True, cliente=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=criar)))).responder("manda")
    resultado = chamadas[1][-1]["content"][0]
    assert resultado["is_error"] and resultado["content"].startswith(tools.PREFIXO_FALHA)


class Roteiro:
    """Respostas em sequência para Prompt.ask / Confirm.ask."""

    def __init__(self, respostas):
        self.respostas = list(respostas)

    def __call__(self, *a, **k):
        return self.respostas.pop(0)


def test_configurar_gmail_nao_salva_recusada_e_deixa_tentar_de_novo(monkeypatch, tmp_path):
    gravados = []
    testes = iter(["enviar e-mails: o Google recusou o endereço ou a senha de app", None])
    monkeypatch.setattr(configurar, "ler_env", lambda: {})
    monkeypatch.setattr(configurar, "gravar_env", lambda d, *a: gravados.append(d))
    monkeypatch.setattr(configurar.webbrowser, "open", lambda url: None)
    monkeypatch.setattr("jarvis.tools.gmail_simples.testar_login", lambda e, s: next(testes))
    monkeypatch.setattr(configurar.Prompt, "ask", Roteiro([
        "Gustavo Silva@gmail.com", "senha-errada",           # 1ª: formato inválido (não testa)
        "gustavo@gmail.com", "abcd efgh ijkl mnop",           # 2ª: Google recusa
        "gustavo@gmail.com", "qrst uvwx yzab cdef",           # 3ª: funciona
    ]))
    monkeypatch.setattr(configurar.Confirm, "ask", Roteiro([True, True]))
    assert configurar.configurar_gmail() is True
    assert gravados == [{"GMAIL_ENDERECO": "gustavo@gmail.com", "GMAIL_SENHA_APP": "qrstuvwxyzabcdef"}]


def test_configurar_gmail_desiste_sem_salvar(monkeypatch):
    gravados = []
    monkeypatch.setattr(configurar, "ler_env", lambda: {})
    monkeypatch.setattr(configurar, "gravar_env", lambda d, *a: gravados.append(d))
    monkeypatch.setattr(configurar.webbrowser, "open", lambda url: None)
    monkeypatch.setattr("jarvis.tools.gmail_simples.testar_login", lambda e, s: "recusou")
    monkeypatch.setattr(configurar.Prompt, "ask", Roteiro(["g@gmail.com", "abcdefghijklmnop"]))
    monkeypatch.setattr(configurar.Confirm, "ask", Roteiro([False]))
    assert configurar.configurar_gmail() is False and gravados == []


def test_teste_da_chave_gemini(api_falsa, monkeypatch):  # noqa: F811
    from google import genai as genai_mod

    api = api_falsa([
        ok({"text": "ok"}),
        (400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}),
    ])
    monkeypatch.setattr(genai_mod, "Client", lambda **kw: api.cliente)
    assert configurar.testar_chave_gemini("AQ.chave", "gemini-flash-latest") == (None, False)
    corpo = api.pedidos[0]
    assert "automaticFunctionCalling" not in str(corpo)  # config local do SDK, não vai na requisição
    erro, invalida = configurar.testar_chave_gemini("AQ.chave", "gemini-flash-latest")
    assert invalida and "chave do Gemini" in erro


def test_teste_da_chave_erro_estranho_nao_culpa_a_chave(monkeypatch):
    from google import genai as genai_mod

    class Quebrado:
        def __init__(self, **kw):
            raise RuntimeError("event loop is closed")

    monkeypatch.setattr(genai_mod, "Client", Quebrado)
    erro, invalida = configurar.testar_chave_gemini("AQ.chave", "gemini-flash-latest")
    assert erro == "RuntimeError: event loop is closed" and invalida is False


def test_formato_da_chave():
    assert configurar.formato_chave_ok("AQ.Exemplo_chave_falsa_1234567890abcdefXYZ")
    assert configurar.formato_chave_ok("AIza" + "B" * 35)
    assert not configurar.formato_chave_ok("sk-ant-123")
