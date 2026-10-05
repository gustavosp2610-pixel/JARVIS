"""Gmail e Google Agenda.

Configuração (uma vez só — passo a passo no README):
1. Crie um projeto no Google Cloud, ative Gmail API e Google Calendar API.
2. Crie uma credencial OAuth do tipo "App para computador" e baixe o JSON.
3. Salve como dados/credentials.json e rode: python -m jarvis --google
"""

from __future__ import annotations

import base64
import logging
import imaplib
import json
import smtplib
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import lru_cache
from typing import Any

from jarvis.config import config
from jarvis.tools import CONFIRMAR, FalhaFerramenta, ferramenta, gmail_simples

log = logging.getLogger("jarvis")

ESCOPOS = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]
CREDENCIAIS = config.pasta_dados / "credentials.json"
TOKEN = config.pasta_dados / "token.json"


class GoogleNaoConfigurado(RuntimeError):
    pass


def autorizar(interativo: bool = False) -> Any:
    """Carrega o token salvo; com interativo=True abre o navegador para login."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), ESCOPOS)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interativo:
        if not CREDENCIAIS.exists():
            raise GoogleNaoConfigurado(f"Arquivo {CREDENCIAIS} não encontrado. Veja o README.")
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = InstalledAppFlow.from_client_secrets_file(str(CREDENCIAIS), ESCOPOS).run_local_server(port=0)
    else:
        raise GoogleNaoConfigurado(
            "Google ainda não configurado. Peça ao usuário para rodar 'python -m jarvis --google'."
        )
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


@lru_cache(maxsize=None)
def _servico(nome: str, versao: str) -> Any:
    from googleapiclient.discovery import build

    return build(nome, versao, credentials=autorizar(), cache_discovery=False)


def _cabecalho(msg: dict, nome: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == nome.lower():
            return h["value"]
    return ""


def _corpo_texto(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for parte in payload.get("parts", []) or []:
        texto = _corpo_texto(parte)
        if texto:
            return texto
    return ""


COMO_CONECTAR = "Para conectar, dê dois cliques em conectar_gmail.bat na pasta do JARVIS e crie uma senha de app nova."


def _senha_recusada(e: Exception) -> bool:
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return True
    texto = str(e).lower()
    return isinstance(e, imaplib.IMAP4.error) and ("authenticationfailed" in texto or "invalid credentials" in texto)


def _protegido(func):
    """Converte erros de configuração/conexão em FalhaFerramenta, com explicação para o usuário."""

    def embrulho(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FalhaFerramenta:
            raise
        except (GoogleNaoConfigurado, gmail_simples.GmailNaoConfigurado) as e:
            raise FalhaFerramenta(str(e)) from e
        except ImportError as e:
            raise FalhaFerramenta("Bibliotecas do Google não instaladas (rode o instalar_jarvis.bat de novo).") from e
        except (smtplib.SMTPException, imaplib.IMAP4.error, OSError) as e:
            if _senha_recusada(e):
                raise FalhaFerramenta(
                    "O Google recusou o login do Gmail (endereço ou senha de app errados). " + COMO_CONECTAR
                ) from e
            log.warning("Gmail falhou em %s: %s: %s", func.__name__, type(e).__name__, e)
            raise FalhaFerramenta(f"Não consegui falar com o Gmail agora ({type(e).__name__}: {e}).") from e

    embrulho.__name__ = func.__name__
    embrulho.__doc__ = func.__doc__
    return embrulho


# ---------------------------------------------------------------------------
# Gmail — usa o OAuth (python -m jarvis --google) se existir; senão a senha de app
# (python -m jarvis --gmail, ver jarvis/tools/gmail_simples.py).
# ---------------------------------------------------------------------------

ARQUIVO_EMAILS = config.pasta_dados / "emails.json"
SEM_GMAIL = "O Gmail ainda não está conectado. " + COMO_CONECTAR


def _usar_oauth() -> bool:
    return TOKEN.exists()


def _sem_acento(texto: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def emails_contatos() -> dict[str, str]:
    try:
        return json.loads(ARQUIVO_EMAILS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolver_destinatarios(para: str) -> list[str]:
    """'meu pai, maria@x.com' -> endereços. Nomes vêm da agenda de e-mails; endereços ditados são limpos."""
    from jarvis.tools.gmail_simples import limpar_endereco

    contatos = {_sem_acento(n): e for n, e in emails_contatos().items()}
    enderecos = []
    for item in re.split(r"[,;]| e (?=\S+@)", para):
        item = item.strip()
        if not item:
            continue
        chave = _sem_acento(item).removeprefix("o ").removeprefix("a ")
        if "@" not in item and "arroba" not in chave:
            achado = contatos.get(chave) or next((e for n, e in contatos.items() if chave and chave in n), None)
            if not achado:
                raise ValueError(
                    f"Não tenho o e-mail de '{item}'. Pergunte o endereço ao usuário e salve com salvar_email_contato."
                )
            enderecos.append(achado)
        else:
            enderecos.append(limpar_endereco(item))
    if not enderecos:
        raise ValueError("Faltou o destinatário do e-mail.")
    return enderecos


def _normalizar_envio(entrada: dict[str, Any]) -> dict[str, Any]:
    entrada["para"] = ", ".join(resolver_destinatarios(str(entrada.get("para", ""))))
    return entrada


@ferramenta(
    "salvar_email_contato",
    "Salva o e-mail de uma pessoa para mandar e-mails pelo nome depois (ex.: nome 'meu pai').",
    {"nome": {"type": "string", "description": "Como o usuário chama a pessoa: 'meu pai', 'Carlos'..."},
     "email": {"type": "string"}},
    ["nome", "email"],
)
def salvar_email_contato(nome: str, email: str) -> str:
    from jarvis.tools.gmail_simples import limpar_endereco

    endereco = limpar_endereco(email)
    contatos = emails_contatos()
    contatos[nome.strip().lower()] = endereco
    ARQUIVO_EMAILS.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_EMAILS.write_text(json.dumps(contatos, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"E-mail salvo: {nome} = {endereco}."


@ferramenta("listar_emails_contatos", "Lista os e-mails de contatos salvos.")
def listar_emails_contatos() -> str:
    contatos = emails_contatos()
    return "\n".join(f"- {n}: {e}" for n, e in sorted(contatos.items())) or "Nenhum e-mail de contato salvo."


@ferramenta(
    "ler_emails_recentes",
    "Lista e-mails recentes do Gmail (remetente, assunto, trecho). Aceita filtros de busca do Gmail, "
    "ex.: 'is:unread', 'from:fulano', 'newer_than:2d'.",
    {
        "filtro": {"type": "string", "description": "Busca do Gmail (padrão: 'in:inbox')."},
        "quantidade": {"type": "integer", "description": "Máximo de e-mails (padrão 5, máx. 20)."},
    },
)
@_protegido
def ler_emails_recentes(filtro: str | None = None, quantidade: int | None = None) -> Any:
    qtd = max(1, min(20, quantidade or 5))
    if not _usar_oauth():
        from jarvis.tools import gmail_simples

        if not gmail_simples.configurado():
            raise FalhaFerramenta(SEM_GMAIL)
        return gmail_simples.recentes(filtro or "in:inbox", qtd) or "Nenhum e-mail encontrado."
    gmail = _servico("gmail", "v1")
    resp = gmail.users().messages().list(userId="me", q=filtro or "in:inbox", maxResults=qtd).execute()
    emails = []
    for item in resp.get("messages", []):
        msg = gmail.users().messages().get(
            userId="me", id=item["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        emails.append(
            {
                "id": msg["id"],
                "de": _cabecalho(msg, "From"),
                "assunto": _cabecalho(msg, "Subject"),
                "data": _cabecalho(msg, "Date"),
                "trecho": msg.get("snippet", ""),
                "nao_lido": "UNREAD" in msg.get("labelIds", []),
            }
        )
    return emails or "Nenhum e-mail encontrado."


@ferramenta(
    "ler_email",
    "Lê o conteúdo completo de um e-mail pelo id (obtido em ler_emails_recentes).",
    {"id": {"type": "string"}},
    ["id"],
)
@_protegido
def ler_email(id: str) -> Any:
    if not _usar_oauth():
        from jarvis.tools import gmail_simples

        if not gmail_simples.configurado():
            raise FalhaFerramenta(SEM_GMAIL)
        return gmail_simples.ler(id)
    msg = _servico("gmail", "v1").users().messages().get(userId="me", id=id, format="full").execute()
    return {
        "de": _cabecalho(msg, "From"),
        "para": _cabecalho(msg, "To"),
        "assunto": _cabecalho(msg, "Subject"),
        "data": _cabecalho(msg, "Date"),
        "corpo": _corpo_texto(msg.get("payload", {}))[:15_000] or msg.get("snippet", ""),
    }


@ferramenta(
    "enviar_email",
    "Envia um e-mail pelo Gmail do usuário. Escreva o assunto e o texto no tom que o usuário pediu "
    "(assine com o nome dele se souber). O usuário vê o e-mail pronto e confirma antes do envio.",
    {
        "para": {
            "type": "string",
            "description": "Endereço(s) separados por vírgula, ou o nome de um contato salvo (ex.: 'meu pai'). "
            "Endereços ditados por voz podem vir com espaços; mande como ouviu.",
        },
        "assunto": {"type": "string"},
        "corpo": {"type": "string"},
    },
    ["para", "assunto", "corpo"],
    risco=CONFIRMAR,
    normalizar=_normalizar_envio,
)
@_protegido
def enviar_email(para: str, assunto: str, corpo: str) -> str:
    destinatarios = resolver_destinatarios(para)
    if not _usar_oauth():
        from jarvis.tools import gmail_simples

        if not gmail_simples.configurado():
            raise FalhaFerramenta(SEM_GMAIL)
        gmail_simples.enviar(destinatarios, assunto, corpo)
        return f"E-mail enviado para {', '.join(destinatarios)}."
    mime = MIMEText(corpo, "plain", "utf-8")
    mime["to"] = ", ".join(destinatarios)
    mime["subject"] = assunto
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    _servico("gmail", "v1").users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"E-mail enviado para {', '.join(destinatarios)}."


# ---------------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------------


@ferramenta(
    "ver_agenda",
    "Lista os próximos compromissos da Google Agenda.",
    {"dias": {"type": "integer", "description": "Quantos dias à frente olhar (padrão 1 = hoje e amanhã cedo)."}},
)
@_protegido
def ver_agenda(dias: int | None = None) -> Any:
    agora = datetime.now().astimezone()
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=max(1, dias or 1))
    resp = _servico("calendar", "v3").events().list(
        calendarId="primary",
        timeMin=inicio.isoformat(),
        timeMax=fim.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()
    eventos = [
        {
            "titulo": e.get("summary", "(sem título)"),
            "inicio": e["start"].get("dateTime", e["start"].get("date")),
            "fim": e["end"].get("dateTime", e["end"].get("date")),
            "local": e.get("location", ""),
        }
        for e in resp.get("items", [])
    ]
    return eventos or "Nenhum compromisso nesse período."


@ferramenta(
    "criar_evento",
    "Cria um compromisso na Google Agenda. Datas no formato ISO, ex.: 2026-10-05T14:00:00.",
    {
        "titulo": {"type": "string"},
        "inicio": {"type": "string", "description": "Data/hora de início ISO 8601 (horário local)."},
        "duracao_minutos": {"type": "integer", "description": "Padrão 60."},
        "descricao": {"type": "string"},
        "local": {"type": "string"},
    },
    ["titulo", "inicio"],
    risco=CONFIRMAR,
)
@_protegido
def criar_evento(
    titulo: str,
    inicio: str,
    duracao_minutos: int | None = None,
    descricao: str | None = None,
    local: str | None = None,
) -> str:
    comeco = datetime.fromisoformat(inicio)
    if comeco.tzinfo is None:
        comeco = comeco.astimezone()
    fim = comeco + timedelta(minutes=duracao_minutos or 60)
    corpo = {
        "summary": titulo,
        "start": {"dateTime": comeco.isoformat()},
        "end": {"dateTime": fim.isoformat()},
    }
    if descricao:
        corpo["description"] = descricao
    if local:
        corpo["location"] = local
    evento = _servico("calendar", "v3").events().insert(calendarId="primary", body=corpo).execute()
    return f"Evento '{titulo}' criado para {comeco:%d/%m às %H:%M}. Link: {evento.get('htmlLink', '')}"
