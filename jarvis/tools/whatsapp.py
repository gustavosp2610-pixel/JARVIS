"""WhatsApp: contatos salvos e envio de mensagens pelo WhatsApp Desktop (ou Web)."""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import webbrowser
from pathlib import Path

from jarvis.config import config
from jarvis.tools import CONFIRMAR, ferramenta

ARQUIVO = config.pasta_dados / "contatos.json"


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def normalizar_numero(numero: str) -> str:
    """'(11) 98765-4321' -> '5511987654321'. Números sem DDI ganham o 55 do Brasil."""
    digitos = re.sub(r"\D", "", numero)
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) in (10, 11):  # DDD + número, sem o 55
        digitos = "55" + digitos
    if not 11 <= len(digitos) <= 15:
        raise ValueError(f"Número inválido: {numero}")
    return digitos


class Contatos:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo

    def todos(self) -> dict[str, str]:
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def salvar(self, nome: str, telefone: str) -> str:
        numero = normalizar_numero(telefone)
        contatos = self.todos()
        contatos[nome.strip()] = numero
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(contatos, ensure_ascii=False, indent=2), encoding="utf-8")
        return numero

    def resolver(self, contato: str) -> tuple[str, str]:
        """Nome salvo ou número -> (nome, número). Levanta LookupError se não achar."""
        if re.search(r"\d{8,}", re.sub(r"\D", "", contato)):
            return contato, normalizar_numero(contato)
        alvo = _sem_acento(contato)
        contatos = self.todos()
        for nome, numero in contatos.items():
            if _sem_acento(nome) == alvo:
                return nome, numero
        parecidos = [(n, num) for n, num in contatos.items() if alvo in _sem_acento(n)]
        if len(parecidos) == 1:
            return parecidos[0]
        if len(parecidos) > 1:
            raise LookupError(f"Mais de um contato parecido: {', '.join(n for n, _ in parecidos)}. Qual deles?")
        raise LookupError(
            f"Não tenho o número de '{contato}'. Peça o número ao usuário e use salvar_contato."
        )


contatos = Contatos(ARQUIVO)


def url_whatsapp(numero: str, mensagem: str, desktop: bool = True) -> str:
    texto = urllib.parse.quote(mensagem)
    if desktop:
        return f"whatsapp://send?phone={numero}&text={texto}"
    return f"https://web.whatsapp.com/send?phone={numero}&text={texto}"


def _abrir_whatsapp(numero: str, mensagem: str) -> str:
    """Abre a conversa com o texto pronto. Devolve 'desktop' ou 'web'."""
    import os
    import sys

    if sys.platform == "win32":
        try:
            os.startfile(url_whatsapp(numero, mensagem))  # type: ignore[attr-defined]
            return "desktop"
        except OSError:
            pass  # WhatsApp Desktop não instalado
    webbrowser.open(url_whatsapp(numero, mensagem, desktop=False))
    return "web"


@ferramenta(
    "salvar_contato",
    "Salva (ou atualiza) o telefone de um contato para usar no WhatsApp.",
    {
        "nome": {"type": "string"},
        "telefone": {"type": "string", "description": "Com DDD, ex.: (11) 98765-4321. DDI opcional."},
    },
    ["nome", "telefone"],
)
def salvar_contato(nome: str, telefone: str) -> str:
    return f"Contato salvo: {nome} ({contatos.salvar(nome, telefone)})."


@ferramenta("listar_contatos", "Lista os contatos salvos para WhatsApp.")
def listar_contatos() -> str:
    todos = contatos.todos()
    return "\n".join(f"- {n}: +{num}" for n, num in sorted(todos.items())) if todos else "Nenhum contato salvo."


@ferramenta(
    "enviar_whatsapp",
    "Envia uma mensagem de WhatsApp para um contato salvo ou um número. Abre o WhatsApp com a mensagem pronta "
    "e aperta Enter para enviar.",
    {
        "contato": {"type": "string", "description": "Nome salvo (ex.: 'João') ou número com DDD."},
        "mensagem": {"type": "string"},
    },
    ["contato", "mensagem"],
    risco=CONFIRMAR,
)
def enviar_whatsapp(contato: str, mensagem: str) -> str:
    try:
        nome, numero = contatos.resolver(contato)
    except (LookupError, ValueError) as e:
        return str(e)
    onde = _abrir_whatsapp(numero, mensagem)
    if not config.whatsapp_enviar_sozinho:
        return f"Conversa com {nome} aberta no WhatsApp {onde} com a mensagem pronta; o usuário envia."
    time.sleep(4 if onde == "desktop" else 15)  # tempo para a janela/página carregar
    try:
        import pyautogui

        pyautogui.press("enter")
    except Exception as e:
        return f"Abri a conversa com {nome} com a mensagem pronta, mas não consegui apertar Enter ({e})."
    return (
        f"Mensagem enviada para {nome} pelo WhatsApp {onde}. "
        "Se puder, tire um screenshot para confirmar que ela saiu."
    )
