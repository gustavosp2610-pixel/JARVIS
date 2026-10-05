"""Gmail sem Google Cloud: SMTP (enviar) e IMAP (ler) com uma "senha de app" do Google.

Como criar a senha de app: https://myaccount.google.com/apppasswords
(a conta precisa ter a verificação em duas etapas ligada). O assistente
`python -m jarvis --gmail` faz isso com o usuário e testa na hora.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

SMTP_HOST, SMTP_PORTA = "smtp.gmail.com", 465
IMAP_HOST = "imap.gmail.com"
PASTA_TODOS = '"[Gmail]/All Mail"'
EMAIL_VALIDO = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


class GmailNaoConfigurado(RuntimeError):
    pass


def credenciais() -> tuple[str, str]:
    endereco = os.getenv("GMAIL_ENDERECO", "").strip()
    senha = os.getenv("GMAIL_SENHA_APP", "").replace(" ", "").strip()
    if not endereco or not senha:
        raise GmailNaoConfigurado(
            "O Gmail ainda não está conectado. Peça ao usuário para rodar o instalar_jarvis.bat "
            "(ou python -m jarvis --gmail) e colar a senha de app do Google."
        )
    return endereco, senha


def configurado() -> bool:
    try:
        credenciais()
        return True
    except GmailNaoConfigurado:
        return False


def limpar_endereco(texto: str) -> str:
    """'Anderson F Silva 73@gmail.com' (ditado por voz) -> 'andersonfsilva73@gmail.com'."""
    t = texto.strip().lower()
    t = re.sub(r"\s*(arroba|\(at\))\s*", "@", t)
    t = re.sub(r"\s+ponto\s+", ".", t)
    t = re.sub(r"\s+", "", t)
    t = t.strip("<>.,;:\"'")
    if not EMAIL_VALIDO.match(t):
        raise ValueError(f"'{texto}' não parece um endereço de e-mail válido. Confirme o endereço com o usuário.")
    return t


def _texto_cabecalho(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:
        return valor


def _corpo_texto(msg: email.message.Message) -> str:
    partes_html = []
    for parte in msg.walk() if msg.is_multipart() else [msg]:
        if parte.get_content_maintype() == "multipart" or parte.get("Content-Disposition", "").startswith("attachment"):
            continue
        dados = parte.get_payload(decode=True)
        if dados is None:
            continue
        texto = dados.decode(parte.get_content_charset() or "utf-8", errors="replace")
        if parte.get_content_type() == "text/plain" and texto.strip():
            return texto
        if parte.get_content_type() == "text/html":
            partes_html.append(texto)
    if partes_html:
        from jarvis.tools.estudos import texto_de_html

        return texto_de_html(partes_html[0])[1]
    return ""


# ---------------------------------------------------------------------------


def testar_login(endereco: str, senha: str) -> str | None:
    """None se o login funcionou; senão, a explicação do problema."""
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORTA, timeout=20) as smtp:
            smtp.login(endereco, senha.replace(" ", ""))
        return None
    except smtplib.SMTPAuthenticationError:
        return ("O Google recusou o login. Confira o e-mail e a senha de app (16 letras) — "
                "a senha normal da conta não funciona aqui.")
    except OSError as e:
        return f"Não consegui falar com o Gmail ({type(e).__name__}). Verifique a internet."


def enviar(para: list[str], assunto: str, corpo: str) -> None:
    endereco, senha = credenciais()
    nome = os.getenv("JARVIS_NOME_USUARIO", "").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((nome, endereco)) if nome and nome.lower() != "senhor" else endereco
    msg["To"] = ", ".join(para)
    msg["Subject"] = assunto
    msg.set_content(corpo)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORTA, timeout=30) as smtp:
        smtp.login(endereco, senha)
        smtp.send_message(msg)


def _conectar() -> imaplib.IMAP4_SSL:
    endereco, senha = credenciais()
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(endereco, senha)
    return imap


def recentes(filtro: str = "in:inbox", quantidade: int = 5) -> list[dict[str, Any]]:
    imap = _conectar()
    try:
        status, _ = imap.select(PASTA_TODOS, readonly=True)
        if status != "OK":
            imap.select("INBOX", readonly=True)
        # X-GM-RAW aceita a mesma busca da caixa do Gmail (is:unread, from:fulano, newer_than:2d...)
        status, dados = imap.uid("SEARCH", "X-GM-RAW", '"' + filtro.replace('"', "") + '"')
        uids = (dados[0] or b"").split() if status == "OK" else []
        resultado = []
        for uid in reversed(uids[-quantidade:]):
            status, partes = imap.uid("FETCH", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] BODY.PEEK[TEXT]<0.400>)")
            if status != "OK" or not partes:
                continue
            cabecalho, trecho, flags = b"", b"", b""
            for item in partes:
                if isinstance(item, tuple):
                    if b"HEADER" in item[0]:
                        cabecalho = item[1]
                        flags += item[0]
                    else:
                        trecho = item[1]
                        flags += item[0]
                elif isinstance(item, bytes):
                    flags += item
            msg = email.message_from_bytes(cabecalho)
            resultado.append({
                "id": uid.decode(),
                "de": _texto_cabecalho(msg.get("From")),
                "assunto": _texto_cabecalho(msg.get("Subject")),
                "data": msg.get("Date", ""),
                "trecho": re.sub(r"\s+", " ", trecho.decode("utf-8", errors="replace"))[:200],
                "nao_lido": b"\\Seen" not in flags,
            })
        return resultado
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def ler(uid: str) -> dict[str, Any]:
    imap = _conectar()
    try:
        status, _ = imap.select(PASTA_TODOS, readonly=True)
        if status != "OK":
            imap.select("INBOX", readonly=True)
        status, partes = imap.uid("FETCH", uid.encode(), "(BODY.PEEK[])")
        bruto = next((p[1] for p in partes or [] if isinstance(p, tuple)), None)
        if status != "OK" or bruto is None:
            raise LookupError("Não encontrei esse e-mail.")
        msg = email.message_from_bytes(bruto)
        return {
            "de": _texto_cabecalho(msg.get("From")),
            "para": _texto_cabecalho(msg.get("To")),
            "assunto": _texto_cabecalho(msg.get("Subject")),
            "data": msg.get("Date", ""),
            "corpo": _corpo_texto(msg)[:15_000],
        }
    finally:
        try:
            imap.logout()
        except Exception:
            pass
