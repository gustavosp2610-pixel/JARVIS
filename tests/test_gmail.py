"""Gmail por senha de app (SMTP/IMAP simulados) e confirmação legível."""

import smtplib
from types import SimpleNamespace

import pytest

from jarvis import tools
from jarvis.brain import Cerebro
from jarvis.tools import gmail_simples, google
from tests.test_gemini import api_falsa  # noqa: F401 (fixture)


@pytest.fixture
def gmail_ligado(monkeypatch, tmp_path):
    monkeypatch.setenv("GMAIL_ENDERECO", "gustavo@gmail.com")
    monkeypatch.setenv("GMAIL_SENHA_APP", "abcd efgh ijkl mnop")
    monkeypatch.setenv("JARVIS_NOME_USUARIO", "Gustavo")
    monkeypatch.setattr(google, "TOKEN", tmp_path / "sem_token.json")  # sem OAuth
    monkeypatch.setattr(google, "ARQUIVO_EMAILS", tmp_path / "emails.json")


class SmtpFalso:
    enviados: list = []
    logins: list = []
    recusar = False

    def __init__(self, host, porta, timeout=None):
        assert (host, porta) == ("smtp.gmail.com", 465)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, usuario, senha):
        if SmtpFalso.recusar:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        SmtpFalso.logins.append((usuario, senha))

    def send_message(self, msg):
        SmtpFalso.enviados.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    SmtpFalso.enviados, SmtpFalso.logins, SmtpFalso.recusar = [], [], False
    monkeypatch.setattr(gmail_simples.smtplib, "SMTP_SSL", SmtpFalso)
    return SmtpFalso


@pytest.mark.parametrize(
    "ditado,esperado",
    [
        ("Anderson F Silva 73@gmail.com", "andersonfsilva73@gmail.com"),
        ("maria arroba hotmail ponto com", "maria@hotmail.com"),
        ("<Joao.Pedro@Empresa.com.br>", "joao.pedro@empresa.com.br"),
    ],
)
def test_limpar_endereco_ditado(ditado, esperado):
    assert gmail_simples.limpar_endereco(ditado) == esperado


def test_endereco_invalido():
    with pytest.raises(ValueError):
        gmail_simples.limpar_endereco("meu pai")


def test_enviar_email_por_senha_de_app(gmail_ligado, smtp):
    r = google.enviar_email("Anderson F Silva 73@gmail.com", "Notícias", "Pai, está tudo bem comigo.")
    assert r == "E-mail enviado para andersonfsilva73@gmail.com."
    assert smtp.logins == [("gustavo@gmail.com", "abcdefghijklmnop")]
    msg = smtp.enviados[0]
    assert msg["To"] == "andersonfsilva73@gmail.com" and msg["Subject"] == "Notícias"
    assert "Gustavo" in msg["From"] and "gustavo@gmail.com" in msg["From"]
    assert msg.get_content().strip() == "Pai, está tudo bem comigo."


def test_contato_por_nome(gmail_ligado, smtp):
    assert "anderson@gmail.com" in google.salvar_email_contato("meu pai", "Anderson@Gmail.com")
    google.enviar_email("meu pai", "Oi", "Tudo bem")
    assert smtp.enviados[0]["To"] == "anderson@gmail.com"
    assert "Não tenho o e-mail de 'tia Ana'" in str(pytest.raises(ValueError, google.resolver_destinatarios, "tia Ana").value)


def test_senha_recusada_vira_mensagem(gmail_ligado, smtp):
    smtp.recusar = True
    assert "recusou a senha de app" in google.enviar_email("a@b.com", "x", "y")


def test_sem_gmail_configurado(monkeypatch, tmp_path):
    monkeypatch.delenv("GMAIL_ENDERECO", raising=False)
    monkeypatch.delenv("GMAIL_SENHA_APP", raising=False)
    monkeypatch.setattr(google, "TOKEN", tmp_path / "x.json")
    assert "não está conectado" in google.enviar_email("a@b.com", "x", "y")
    assert "não está conectado" in google.ler_emails_recentes()


def test_testar_login(smtp):
    assert gmail_simples.testar_login("a@gmail.com", "x y") is None
    smtp.recusar = True
    assert "recusou o login" in gmail_simples.testar_login("a@gmail.com", "x")


class ImapFalso:
    def __init__(self, host):
        self.comandos = []

    def login(self, u, s):
        pass

    def select(self, pasta, readonly=False):
        assert readonly
        return "OK", [b"3"]

    def uid(self, comando, *args):
        self.comandos.append((comando, args))
        if comando == "SEARCH":
            assert args == ("X-GM-RAW", '"is:unread in:inbox"')
            return "OK", [b"7 8"]
        if "BODY.PEEK[]" in args[1]:
            bruto = (b"From: Ana <ana@x.com>\r\nTo: g@gmail.com\r\nSubject: =?utf-8?q?Reuni=C3=A3o?=\r\n"
                     b"Content-Type: text/html; charset=utf-8\r\n\r\n<p>Amanh\xc3\xa3 \xc3\xa0s 10h</p>")
            return "OK", [(b"8 (UID 8 BODY[] {100}", bruto), b")"]
        assert "BODY.PEEK[HEADER.FIELDS" in args[1]
        cab = b"From: Ana <ana@x.com>\r\nSubject: =?utf-8?q?Reuni=C3=A3o?=\r\nDate: Mon, 5 Oct 2026 10:00 -0300\r\n\r\n"
        flags = b"(\\Seen)" if args[0] == b"7" else b"()"
        return "OK", [(b"1 (UID " + args[0] + b" FLAGS " + flags + b" BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80}", cab),
                      (b" BODY[TEXT]<0> {20}", b"Ola, tudo certo?"), b")"]

    def logout(self):
        pass


def test_ler_emails_por_imap(gmail_ligado, monkeypatch):
    monkeypatch.setattr(gmail_simples.imaplib, "IMAP4_SSL", ImapFalso)
    emails = google.ler_emails_recentes("is:unread in:inbox", 5)
    assert [e["id"] for e in emails] == ["8", "7"]  # mais recente primeiro
    assert emails[0]["assunto"] == "Reunião" and emails[0]["de"] == "Ana <ana@x.com>"
    assert emails[0]["nao_lido"] is True and emails[1]["nao_lido"] is False
    assert emails[0]["trecho"] == "Ola, tudo certo?"
    lido = google.ler_email("8")
    assert lido["corpo"] == "Amanhã às 10h" and lido["assunto"] == "Reunião"


def test_confirmacao_mostra_endereco_ja_limpo(gmail_ligado, smtp):
    perguntas = []
    respostas = [
        ("tool_use", [SimpleNamespace(type="tool_use", name="enviar_email", id="t1",
                                      input={"para": "Anderson F Silva 73@gmail.com", "assunto": "Oi", "corpo": "Tudo bem"})]),
        ("end_turn", [SimpleNamespace(type="text", text="Enviado.")]),
    ]

    class Cliente:
        beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            stop_reason=respostas[0][0], content=respostas.pop(0)[1])))

    Cerebro(lambda r: perguntas.append(r) or True, cliente=Cliente()).responder("manda email pro meu pai")
    assert perguntas == ["enviar_email(para: andersonfsilva73@gmail.com\nassunto: Oi\ncorpo: Tudo bem)"]
    assert smtp.enviados[0]["To"] == "andersonfsilva73@gmail.com"


def test_endereco_invalido_nao_pede_confirmacao(gmail_ligado, smtp):
    perguntas = []
    respostas = [
        ("tool_use", [SimpleNamespace(type="tool_use", name="enviar_email", id="t1",
                                      input={"para": "fulano", "assunto": "Oi", "corpo": "x"})]),
        ("end_turn", [SimpleNamespace(type="text", text="Qual o e-mail?")]),
    ]
    chamadas = []

    def criar(**kw):
        chamadas.append({**kw, "messages": list(kw["messages"])})
        stop, conteudo = respostas.pop(0)
        return SimpleNamespace(stop_reason=stop, content=conteudo)

    Cerebro(lambda r: perguntas.append(r) or True, cliente=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=criar)))).responder("manda pro fulano")
    assert perguntas == [] and smtp.enviados == []
    resultado = chamadas[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] and "Não tenho o e-mail" in resultado["content"]
    assert tools.REGISTRO["enviar_email"].risco == tools.CONFIRMAR


def test_gemini_tambem_confirma_endereco_limpo(gmail_ligado, smtp, api_falsa):  # noqa: F811
    from jarvis.cerebro_gemini import CerebroGemini
    from tests.test_gemini import ControleFalso, chamada, ok

    api = api_falsa([
        ok(chamada("enviar_email", {"para": "Anderson F Silva 73@gmail.com", "assunto": "Oi", "corpo": "Tudo bem"})),
        ok({"text": "Enviado, senhor."}),
    ])
    perguntas = []
    c = CerebroGemini(lambda r: perguntas.append(r) or True, cliente=api.cliente, controle_pc=ControleFalso())
    assert c.responder("manda email pro meu pai") == "Enviado, senhor."
    assert perguntas[0].startswith("enviar_email(para: andersonfsilva73@gmail.com\n")
    assert smtp.enviados[0]["To"] == "andersonfsilva73@gmail.com"
