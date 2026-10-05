"""Testes da voz, tarefas/lembretes, WhatsApp e controle do PC (computer use)."""

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from PIL import Image

from jarvis import preferencias, tools
from jarvis.brain import Cerebro
from jarvis.tarefas import Agendador, Tarefas, proxima_ocorrencia
from jarvis.tools import controle as ctl_mod
from jarvis.tools import whatsapp
from jarvis.tools.controle import Controle, ParadaSolicitada, calcular_escala, converter_combinacao
from jarvis.voice.speaker import dividir_frases, preparar_para_fala

# ---------------------------------------------------------------------------
# Voz
# ---------------------------------------------------------------------------


def test_preparar_para_fala_limpa_simbolos_e_links():
    t = preparar_para_fala("**Pronto!** O dólar está R$ 5,32 (alta de 2%). Veja https://exemplo.com/x")
    assert "**" not in t and "https" not in t
    assert "5,32 reais" in t and "2 por cento" in t and "o link na tela" in t


def test_preparar_para_fala_encurta_textos_longos():
    longo = "Frase de teste bem comprida. " * 80
    t = preparar_para_fala(longo, limite=300)
    assert len(t) < 400 and t.endswith("O resto está na tela, senhor.")


def test_dividir_frases_junta_frases_curtas():
    frases = dividir_frases("Sim. Claro. O tempo hoje está ensolarado com máxima de trinta graus. Algo mais?")
    assert frases[0].startswith("Sim. Claro. O tempo")
    assert all(f.strip() for f in frases)


def test_preferencias_de_voz_validam_e_viram_prosodia():
    preferencias.salvar({"voz": "pt-BR-FranciscaNeural", "velocidade": 99, "tom": -5})
    assert preferencias.prosodia() == ("pt-BR-FranciscaNeural", "+50%", "-5Hz")
    with pytest.raises(ValueError):
        preferencias.salvar({"voz": "x; rm -rf /"})


# ---------------------------------------------------------------------------
# Tarefas e lembretes
# ---------------------------------------------------------------------------


@pytest.fixture
def lista(tmp_path):
    return Tarefas(tmp_path / "tarefas.json")


def test_tarefas_adicionar_concluir_apagar(lista):
    lista.adicionar_tarefa("Comprar pão")
    t = lista.adicionar_tarefa("Pagar a luz", "2030-01-10T18:00")
    assert [x["titulo"] for x in lista.tarefas()] == ["Pagar a luz", "Comprar pão"]
    assert lista.concluir_tarefa("pão")["feita"] is True
    assert [x["titulo"] for x in lista.tarefas()] == ["Pagar a luz"]
    assert len(lista.tarefas(incluir_feitas=True)) == 2
    assert lista.apagar_tarefa(t["id"])["titulo"] == "Pagar a luz"
    assert lista.concluir_tarefa("inexistente") is None


def test_lembrete_unico_dispara_uma_vez(lista):
    quando = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat()
    lista.criar_lembrete("tirar o bolo", quando)
    assert lista.vencidos() == []
    disparados = lista.vencidos(datetime.now().astimezone() + timedelta(minutes=11))
    assert [d["mensagem"] for d in disparados] == ["tirar o bolo"]
    assert disparados[0]["atrasado"] is False
    assert lista.lembretes() == []


def test_lembrete_diario_reagenda_e_atrasado(lista):
    base = datetime.now().astimezone() + timedelta(minutes=5)
    lista.criar_lembrete("beber água", base.isoformat(), "diario")
    disparados = lista.vencidos(base + timedelta(hours=2))
    assert disparados[0]["atrasado"] is True
    proximo = datetime.fromisoformat(lista.lembretes()[0]["quando"])
    assert proximo == base + timedelta(days=1)


def test_lembrete_no_passado_e_rejeitado(lista):
    with pytest.raises(ValueError):
        lista.criar_lembrete("x", "2001-01-01T10:00")


def test_dias_uteis_pula_fim_de_semana():
    sexta = datetime(2026, 10, 9, 8, 0).astimezone()
    assert proxima_ocorrencia(sexta, "dias_uteis", sexta).weekday() == 0  # segunda
    assert proxima_ocorrencia(sexta, "semanal", sexta) == sexta + timedelta(weeks=1)
    assert proxima_ocorrencia(sexta, "nunca", sexta) is None


def test_agendador_avisa(monkeypatch, lista):
    from jarvis import tarefas as mod

    monkeypatch.setattr(mod, "tarefas", lista)
    quando = datetime.now().astimezone() + timedelta(minutes=2)
    lista.criar_lembrete("reunião", quando.isoformat())
    avisos = []
    ag = Agendador(avisos.append)
    ag.checar()
    assert avisos == []
    monkeypatch.setattr(mod, "_agora", lambda: quando + timedelta(seconds=5))
    ag.checar()
    ag.checar()
    assert avisos == ["Lembrete: reunião"]


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [("(11) 98765-4321", "5511987654321"), ("+55 21 3333-4444", "552133334444"), ("0044 20 7946 0958", "442079460958")],
)
def test_normalizar_numero(entrada, esperado):
    assert whatsapp.normalizar_numero(entrada) == esperado


def test_contatos_e_url(tmp_path):
    c = whatsapp.Contatos(tmp_path / "c.json")
    c.salvar("João Silva", "11 98765-4321")
    c.salvar("Maria", "21 99999-0000")
    assert c.resolver("joao silva") == ("João Silva", "5511987654321")
    assert c.resolver("joão") == ("João Silva", "5511987654321")
    assert c.resolver("11 91234-5678")[1] == "5511912345678"
    with pytest.raises(LookupError):
        c.resolver("Pedro")
    url = whatsapp.url_whatsapp("5511987654321", "Chego em 10 min!")
    assert url == "whatsapp://send?phone=5511987654321&text=Chego%20em%2010%20min%21"


def test_enviar_whatsapp_sem_envio_automatico(monkeypatch, tmp_path):
    c = whatsapp.Contatos(tmp_path / "c.json")
    c.salvar("Ana", "11 98765-4321")
    monkeypatch.setattr(whatsapp, "contatos", c)
    abertos = []
    monkeypatch.setattr(whatsapp, "_abrir_whatsapp", lambda n, m: abertos.append((n, m)) or "desktop")
    monkeypatch.setattr(whatsapp.config, "whatsapp_enviar_sozinho", False)
    r = whatsapp.enviar_whatsapp("ana", "oi")
    assert abertos == [("5511987654321", "oi")] and "mensagem pronta" in r
    assert tools.REGISTRO["enviar_whatsapp"].risco == tools.CONFIRMAR


# ---------------------------------------------------------------------------
# Controle do PC
# ---------------------------------------------------------------------------


class PyAutoGuiFalso:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        return lambda *a, **k: self.chamadas.append((nome, a, k))

    def position(self):
        return (100, 200)


@pytest.fixture
def pc():
    pg = PyAutoGuiFalso()
    return Controle(pyautogui=pg, grab=lambda regiao=None: Image.new("RGB", (2560, 1440) if regiao is None else (200, 100))), pg


def test_teclas_e_escala():
    assert converter_combinacao("ctrl+shift+Escape") == ["ctrl", "shift", "esc"]
    assert converter_combinacao("Return") == ["enter"]
    assert converter_combinacao("super") == ["win"]
    assert calcular_escala(1280, 720) == 1.0
    e = calcular_escala(2560, 1440)
    assert 2560 * e <= 1568 and 2560 * 1440 * e * e <= 1_150_001


def test_screenshot_reduz_e_cliques_voltam_para_pixels_reais(pc):
    controle, pg = pc
    img = controle.screenshot()
    assert img[0]["type"] == "image" and img[0]["source"]["media_type"] == "image/jpeg"
    x = round(1000 * controle.escala)
    controle.executar("left_click", {"coordinate": [x, 0]})
    nome, _, kw = pg.chamadas[-1]
    assert nome == "click" and abs(kw["x"] - 1000) <= 2 and kw["clicks"] == 1
    controle.executar("double_click", {"coordinate": [10, 10], "text": "ctrl"})
    assert ("keyDown", ("ctrl",), {}) in pg.chamadas and pg.chamadas[-1][0] == "keyUp"
    assert controle.executar("zoom", {"region": [0, 0, 100, 50]})[0]["type"] == "image"
    assert controle.executar("cursor_position", {}).startswith("X=")


def test_digitar_usa_area_de_transferencia(pc, monkeypatch):
    import pyperclip

    copiados = []
    monkeypatch.setattr(pyperclip, "copy", copiados.append)
    monkeypatch.setattr(pyperclip, "paste", lambda: "antigo")
    controle, pg = pc
    controle.executar("type", {"text": "Olá, coração!"})
    assert copiados == ["Olá, coração!", "antigo"]
    assert ("hotkey", ("ctrl", "v"), {}) in pg.chamadas
    controle.executar("key", {"text": "ctrl+s", "repeat": 2})
    assert pg.chamadas[-2:] == [("hotkey", ("ctrl", "s"), {})] * 2


def test_parar_interrompe(pc):
    controle, _ = pc
    controle.parar = True
    with pytest.raises(ParadaSolicitada):
        controle.executar("left_click", {"coordinate": [1, 1]})


# ---------------------------------------------------------------------------
# Cérebro com o toolset de computador
# ---------------------------------------------------------------------------


def acao(nome, entrada, id_):
    return SimpleNamespace(type="tool_use", name=nome, input=entrada, id=id_, toolset_name="computer")


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.chamadas.append({**kw, "messages": list(kw["messages"])})
        stop, conteudo = self.respostas.pop(0)
        return SimpleNamespace(stop_reason=stop, content=conteudo)


class ControleFalso:
    def __init__(self, falhar=None):
        self.feitas = []
        self.parar = False
        self.falhar = falhar

    def descrever(self, nome, entrada):
        return nome

    def executar(self, nome, entrada):
        if nome == self.falhar:
            raise RuntimeError("botão não encontrado")
        self.feitas.append(nome)
        return [{"type": "image", "source": {}}] if nome == "screenshot" else "OK"


def texto(t):
    return SimpleNamespace(type="text", text=t)


def test_toolset_no_pedido_e_toolset_name_nos_resultados():
    cliente = ClienteFalso(
        [
            ("tool_use", [SimpleNamespace(type="thinking", thinking="Abrindo o bloco de notas"),
                          acao("screenshot", {}, "a"), acao("left_click", {"coordinate": [5, 5]}, "b")]),
            ("tool_use", [acao("type", {"text": "oi"}, "c")]),
            ("end_turn", [texto("Pronto.")]),
        ]
    )
    perguntas, notas = [], []
    pc = ControleFalso()
    c = Cerebro(lambda r: perguntas.append(r) or True, cliente=cliente, controle_pc=pc, ao_progresso=notas.append)
    assert c.responder("escreve oi no bloco de notas") == "Pronto."
    assert {"type": "computer_toolset_20260801"} in cliente.chamadas[0]["tools"]
    assert cliente.chamadas[0]["thinking"]["display"] == "updates"
    resultados = cliente.chamadas[1]["messages"][-1]["content"]
    assert all(r["toolset_name"] == "computer" for r in resultados)
    assert pc.feitas == ["screenshot", "left_click", "type"]
    assert len(perguntas) == 1 and perguntas[0].startswith("controlar_mouse_e_teclado")  # uma vez só
    assert notas == ["Abrindo o bloco de notas"]


def test_somente_olhar_a_tela_nao_pede_autorizacao():
    cliente = ClienteFalso([("tool_use", [acao("screenshot", {}, "a")]), ("end_turn", [texto("É um erro de Python.")])])
    perguntas = []
    Cerebro(lambda r: perguntas.append(r) or True, cliente=cliente, controle_pc=ControleFalso()).responder("o que tem na tela?")
    assert perguntas == []


def test_recusa_de_controle_nao_executa_nada():
    cliente = ClienteFalso(
        [("tool_use", [acao("left_click", {"coordinate": [1, 1]}, "a"), acao("type", {"text": "x"}, "b")]),
         ("end_turn", [texto("Tudo bem.")])]
    )
    pc = ControleFalso()
    Cerebro(lambda r: False, cliente=cliente, controle_pc=pc).responder("clica ali")
    resultados = cliente.chamadas[1]["messages"][-1]["content"]
    assert pc.feitas == [] and all(r["is_error"] for r in resultados)
    assert resultados[1]["content"] == ctl_mod.NAO_EXECUTADO


def test_lote_para_no_primeiro_erro():
    cliente = ClienteFalso(
        [("tool_use", [acao("left_click", {"coordinate": [1, 1]}, "a"), acao("type", {"text": "x"}, "b")]),
         ("end_turn", [texto("Não deu.")])]
    )
    pc = ControleFalso(falhar="left_click")
    Cerebro(lambda r: True, cliente=cliente, controle_pc=pc).responder("clica")
    r1, r2 = cliente.chamadas[1]["messages"][-1]["content"]
    assert "botão não encontrado" in r1["content"] and r1["is_error"]
    assert r2["content"] == ctl_mod.NAO_EXECUTADO and pc.feitas == []


def test_botao_parar_interrompe_entre_passos():
    pc = ControleFalso()
    c = None

    class ClienteQueParou(ClienteFalso):
        def _create(self, **kw):
            r = super()._create(**kw)
            c.parar()  # usuário aperta Parar enquanto o Claude pensa
            return r

    cliente = ClienteQueParou([("tool_use", [acao("screenshot", {}, "a")]), ("end_turn", [texto("nunca chega")])])
    c = Cerebro(lambda r: True, cliente=cliente, controle_pc=pc)
    assert c.responder("faz um monte de coisa") == "Parei, senhor."
    assert len(cliente.chamadas) == 1
    assert c.mensagens[-1] == {"role": "assistant", "content": "Parei a pedido do usuário."}


# ---------------------------------------------------------------------------
# Rotas novas do servidor
# ---------------------------------------------------------------------------


def test_rotas_novas_do_servidor(monkeypatch):
    from jarvis.tarefas import tarefas
    from jarvis.web import server

    paradas = []

    class CerebroFalso:
        def __init__(self, confirmar, **kw):
            pass

        def parar(self):
            paradas.append(True)

    monkeypatch.setattr("jarvis.brain.Cerebro", CerebroFalso)
    srv, token = server.criar_servidor(porta=0, agendar=False)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def req(caminho, corpo=None, tok=token):
        r = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=json.dumps(corpo).encode() if corpo is not None else None)
        r.add_header("Host", f"127.0.0.1:{porta}")
        r.add_header("Content-Type", "application/json")
        if tok:
            r.add_header("X-Jarvis-Token", tok)
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read())

    try:
        for rota in ("/api/parar", "/api/preferencias", "/api/tarefas/concluir"):
            with pytest.raises(urllib.error.HTTPError) as e:
                req(rota, {}, tok=None)
            assert e.value.code == 403
        assert req("/api/parar", {}) == {"ok": True} and paradas == [True]
        assert req("/api/preferencias", {"velocidade": 10})["velocidade"] == 10
        t = tarefas.adicionar_tarefa("Testar o servidor")
        assert any(x["id"] == t["id"] for x in req("/api/painel")["tarefas"])
        assert req("/api/tarefas/concluir", {"id": t["id"]}) == {"ok": True}
        assert all(x["id"] != t["id"] for x in req("/api/painel")["tarefas"])
    finally:
        srv.shutdown()
        srv.server_close()
