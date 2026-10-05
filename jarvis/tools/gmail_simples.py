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
EMAIL_VALIDO = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


class GmailNaoConfigurado(RuntimeError):
    pass


def credenciais() -> tuple[str, str]:
    endereco = os.getenv("GMAIL_ENDERECO", "").strip()
    senha = os.getenv("GMAIL_SENHA_APP", "").replace(" ", "").strip()
    if not endereco or not senha:
        raise GmailNaoConfigurado(
            "O Gmail ainda não está conectado. Para conectar, dê dois cliques em conectar_gmail.bat "
            "na pasta do JARVIS e crie uma senha de app."
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


def _explicar(e: Exception) -> str:
    texto = str(e).lower()
    if isinstance(e, smtplib.SMTPAuthenticationError) or "authenticationfailed" in texto or "invalid credentials" in texto:
        return "o Google recusou o endereço ou a senha de app"
    if isinstance(e, OSError):
        return f"sem conexão com o Gmail ({type(e).__name__})"
    return f"{type(e).__name__}: {e}"


def diagnosticar(endereco: str, senha: str) -> dict[str, str | None]:
    """Testa envio (SMTP) e leitura (IMAP). Cada chave vale None se funcionou, ou a explicação do erro."""
    senha = senha.replace(" ", "")
    resultado: dict[str, str | None] = {}
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORTA, timeout=20) as smtp:
            smtp.login(endereco, senha)
        resultado["envio"] = None
    except Exception as e:
        resultado["envio"] = _explicar(e)
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=20)
        try:
            imap.login(endereco, senha)
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        resultado["leitura"] = None
    except Exception as e:
        resultado["leitura"] = _explicar(e)
    return resultado


def testar_login(endereco: str, senha: str) -> str | None:
    """None se envio e leitura funcionaram; senão, a explicação do primeiro problema."""
    d = diagnosticar(endereco, senha)
    erros = [f"{'enviar' if k == 'envio' else 'ler'} e-mails: {v}" for k, v in d.items() if v]
    return "; ".join(erros) or None


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
    imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=20)
    imap.login(endereco, senha)
    return imap


def pasta_todos(imap: Any) -> str:
    """Pasta 'Todos os e-mails' (nome muda com o idioma da conta), achada pelo atributo \\All."""
    try:
        status, linhas = imap.list()
    except Exception:
        return "INBOX"
    for linha in linhas or [] if status == "OK" else []:
        texto = linha.decode("utf-8", "replace") if isinstance(linha, bytes) else str(linha)
        if "\\All" in texto:
            achado = re.search(r'"([^"]+)"\s*$', texto) or re.search(r"(\S+)\s*$", texto)
            if achado:
                return '"' + achado.group(1) + '"'
    return "INBOX"


def _selecionar(imap: Any) -> None:
    status, _ = imap.select(pasta_todos(imap), readonly=True)
    if status != "OK":
        imap.select("INBOX", readonly=True)


def recentes(filtro: str = "in:inbox", quantidade: int = 5) -> list[dict[str, Any]]:
    imap = _conectar()
    try:
        _selecionar(imap)
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
        _selecionar(imap)
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
