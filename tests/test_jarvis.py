from types import SimpleNamespace

import pytest

from jarvis import tools
from jarvis.brain import Cerebro
from jarvis.memory import Memoria
from jarvis.voice.listener import extrair_comando


# ---------------------------------------------------------------------------
# Cliente Claude falso
# ---------------------------------------------------------------------------


def texto(t):
    return SimpleNamespace(type="text", text=t)


def uso(nome, entrada, id_="t1"):
    return SimpleNamespace(type="tool_use", name=nome, input=entrada, id=id_)


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append({**kwargs, "messages": list(kwargs["messages"])})
        stop, conteudo = self.respostas.pop(0)
        return SimpleNamespace(stop_reason=stop, content=conteudo)


@pytest.fixture
def registrar_teste():
    executadas = []

    @tools.ferramenta("_teste_seguro", "teste", {"x": {"type": "string"}}, ["x"])
    def seguro(x):
        executadas.append(("seguro", x))
        return f"ok {x}"

    @tools.ferramenta("_teste_perigoso", "teste", {"x": {"type": "string"}}, ["x"], risco=tools.CONFIRMAR)
    def perigoso(x):
        executadas.append(("perigoso", x))
        return "apagado"

    yield executadas
    tools.REGISTRO.pop("_teste_seguro")
    tools.REGISTRO.pop("_teste_perigoso")


# ---------------------------------------------------------------------------


def test_todas_ferramentas_tem_schema_valido():
    tools.carregar_todas()
    nomes = {s["name"] for s in tools.schemas()}
    assert {"abrir_programa", "enviar_email", "ver_agenda", "lembrar", "apagar_arquivo"} <= nomes
    for s in tools.schemas():
        props = s["input_schema"]["properties"]
        assert set(s["input_schema"]["required"]) <= set(props), s["name"]
    assert tools.REGISTRO["enviar_email"].risco == tools.CONFIRMAR
    assert tools.REGISTRO["apagar_arquivo"].risco == tools.CONFIRMAR
    assert tools.REGISTRO["abrir_programa"].risco == tools.SEGURO


def test_schemas_em_ordem_estavel():
    tools.carregar_todas()
    assert tools.schemas() == tools.schemas()
    nomes = [s["name"] for s in tools.schemas()]
    assert nomes == sorted(nomes)


def test_resposta_simples():
    cliente = ClienteFalso([("end_turn", [texto("Bom dia, senhor.")])])
    c = Cerebro(confirmar=lambda r: True, cliente=cliente)
    assert c.responder("bom dia") == "Bom dia, senhor."
    chamada = cliente.chamadas[0]
    assert chamada["model"] == "claude-opus-5-5"
    assert chamada["thinking"]["type"] == "adaptive"
    assert "[Agora:" in chamada["messages"][0]["content"]


def test_ferramenta_segura_executa_sem_perguntar(registrar_teste):
    perguntas = []
    cliente = ClienteFalso(
        [
            ("tool_use", [uso("_teste_seguro", {"x": "a"})]),
            ("end_turn", [texto("Pronto.")]),
        ]
    )
    c = Cerebro(confirmar=lambda r: perguntas.append(r) or True, cliente=cliente)
    assert c.responder("faz") == "Pronto."
    assert registrar_teste == [("seguro", "a")]
    assert perguntas == []
    resultado = cliente.chamadas[1]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "t1" and resultado["content"] == "ok a"


def test_ferramenta_sensivel_pede_confirmacao_e_respeita_recusa(registrar_teste):
    cliente = ClienteFalso(
        [
            ("tool_use", [uso("_teste_perigoso", {"x": "b"})]),
            ("end_turn", [texto("Entendido, não apaguei.")]),
        ]
    )
    perguntas = []
    c = Cerebro(confirmar=lambda r: perguntas.append(r) or False, cliente=cliente)
    c.responder("apaga")
    assert perguntas == ["_teste_perigoso(x='b')"]
    assert registrar_teste == []
    assert "NÃO autorizou" in cliente.chamadas[1]["messages"][-1]["content"][0]["content"]


def test_ferramenta_sensivel_executa_quando_autorizada(registrar_teste):
    cliente = ClienteFalso(
        [("tool_use", [uso("_teste_perigoso", {"x": "c"})]), ("end_turn", [texto("Feito.")])]
    )
    Cerebro(confirmar=lambda r: True, cliente=cliente).responder("apaga")
    assert registrar_teste == [("perigoso", "c")]


def test_erro_na_ferramenta_volta_como_is_error(registrar_teste):
    cliente = ClienteFalso(
        [("tool_use", [uso("_teste_seguro", {})]), ("end_turn", [texto("Falhou.")])]
    )
    Cerebro(confirmar=lambda r: True, cliente=cliente).responder("faz")
    resultado = cliente.chamadas[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True


def test_recusa_desfaz_o_turno():
    cliente = ClienteFalso([("refusal", [])])
    c = Cerebro(confirmar=lambda r: True, cliente=cliente)
    assert "não posso" in c.responder("algo")
    assert c.mensagens == []


def test_memoria(tmp_path):
    m = Memoria(tmp_path / "m.json")
    assert m.fatos() == []
    m.lembrar("Gosta de café sem açúcar")
    assert m.lembrar("gosta de café sem açúcar") == "Já estava na memória."
    assert m.fatos() == ["Gosta de café sem açúcar"]
    assert "1" in m.esquecer("café")
    assert m.fatos() == []


@pytest.mark.parametrize(
    "frase,esperado",
    [
        ("Jarvis abre o Chrome", "abre o Chrome"),
        ("ei Jarvis, que horas são?", "que horas são"),
        ("Jarbas toca uma música", "toca uma música"),
        ("Jarvis", ""),
        ("abre o chrome", None),
    ],
)
def test_palavra_de_ativacao(frase, esperado):
    assert extrair_comando(frase, "jarvis") == esperado


def test_caminhos_fora_da_pasta_do_usuario_sao_bloqueados():
    from jarvis.tools.computer import HOME, resolver_caminho

    assert resolver_caminho("downloads").name in {"Downloads"}
    assert resolver_caminho("~") == HOME.resolve()
    with pytest.raises(PermissionError):
        resolver_caminho("/etc/passwd")
    with pytest.raises(PermissionError):
        resolver_caminho("../../etc")


def test_servidor_web_exige_token_e_host(monkeypatch):
    import json
    import threading
    import urllib.error
    import urllib.request

    from jarvis.web import server

    class CerebroFalso:
        def __init__(self, confirmar, **callbacks):
            self.confirmar = confirmar

        def parar(self):
            pass

        def responder(self, texto):
            return "eco: " + texto if not self.confirmar("teste(x=1)") else "autorizado"

        def nova_conversa(self):
            pass

    monkeypatch.setattr("jarvis.brain.criar_cerebro", CerebroFalso)
    srv, token = server.criar_servidor(porta=0, agendar=False)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{porta}"

    def req(caminho, corpo=None, tok=token, host=f"127.0.0.1:{porta}"):
        r = urllib.request.Request(base + caminho, data=json.dumps(corpo).encode() if corpo else None)
        r.add_header("Host", host)
        r.add_header("Content-Type", "application/json")
        if tok:
            r.add_header("X-Jarvis-Token", tok)
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read())

    try:
        for kwargs in ({"tok": None}, {"tok": "errado"}, {"host": "evil.com"}):
            with pytest.raises(urllib.error.HTTPError) as e:
                req("/api/painel", **kwargs)
            assert e.value.code == 403

        assert "sistema" in req("/api/painel")
        assert req("/api/mensagem", {"texto": "oi"}) == {"ok": True}
        ev = req("/api/eventos?desde=0&espera=5")["eventos"]
        assert ev[0]["tipo"] == "confirmar" and ev[0]["acao"] == "teste"
        assert req("/api/confirmar", {"id": ev[0]["id"], "aprovado": True}) == {"ok": True}
        tipos = []
        for _ in range(5):
            tipos = [e["tipo"] for e in req("/api/eventos?desde=0&espera=2")["eventos"]]
            if "resposta" in tipos:
                break
        eventos = req("/api/eventos?desde=0&espera=0")["eventos"]
        assert eventos[-1] == {**eventos[-1], "tipo": "resposta", "texto": "autorizado"}
    finally:
        srv.shutdown()
        srv.server_close()
