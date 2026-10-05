"""Rotinas: um nome ("modo trabalho") que dispara vários passos de uma vez.

Os passos ficam em linguagem natural ("abrir o Spotify", "volume em 30"); quando o
usuário pede a rotina, o cérebro recebe a lista e executa cada passo com as
ferramentas que já tem.
"""

from __future__ import annotations

import json
import threading
import unicodedata
from pathlib import Path
from typing import Any

from jarvis.config import config
from jarvis.tools import ferramenta

EXEMPLOS: dict[str, list[str]] = {
    "bom dia": [
        "Dizer bom dia ao usuário",
        "Ver a previsão do tempo de hoje",
        "Ver a agenda de hoje",
        "Ver os e-mails não lidos e citar só os importantes",
        "Listar as tarefas pendentes",
        "Ver a cotação do dólar",
        "Resumir tudo em poucas frases",
    ],
    "modo trabalho": [
        "Abrir o navegador no Gmail (mail.google.com)",
        "Abrir o Google Agenda (calendar.google.com)",
        "Colocar o volume em 30",
        "Listar as tarefas pendentes",
    ],
    "modo foco": [
        "Colocar o volume em 15",
        "Pausar a música se estiver tocando",
        "Iniciar um pomodoro de 25 minutos de foco e 5 de pausa",
        "Avisar que o modo foco começou",
    ],
}


def _chave(nome: str) -> str:
    return unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower().strip()


class Rotinas:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self.trava = threading.RLock()

    def _ler(self) -> dict[str, list[str]]:
        with self.trava:
            if not self.arquivo.exists():
                self._gravar(EXEMPLOS)  # primeira vez: cria os exemplos
                return {k: list(v) for k, v in EXEMPLOS.items()}
            try:
                return json.loads(self.arquivo.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}

    def _gravar(self, dados: dict[str, list[str]]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    def todas(self) -> dict[str, list[str]]:
        return self._ler()

    def nomes(self) -> list[str]:
        return list(self._ler())

    def achar(self, nome: str) -> tuple[str, list[str]] | None:
        alvo = _chave(nome).removeprefix("rotina ").removeprefix("a rotina ").strip()
        dados = self._ler()
        for n, passos in dados.items():
            if _chave(n) == alvo:
                return n, passos
        parecidas = [(n, p) for n, p in dados.items() if alvo and (alvo in _chave(n) or _chave(n) in alvo)]
        return parecidas[0] if len(parecidas) == 1 else None

    def salvar(self, nome: str, passos: list[str]) -> None:
        passos = [str(p).strip() for p in passos if str(p).strip()]
        if not nome.strip() or not passos:
            raise ValueError("A rotina precisa de um nome e de pelo menos um passo.")
        with self.trava:
            dados = self._ler()
            existente = self.achar(nome)
            if existente:
                del dados[existente[0]]
            dados[nome.strip().lower()] = passos
            self._gravar(dados)

    def apagar(self, nome: str) -> str | None:
        with self.trava:
            achada = self.achar(nome)
            if not achada:
                return None
            dados = self._ler()
            del dados[achada[0]]
            self._gravar(dados)
            return achada[0]


rotinas = Rotinas(config.pasta_dados / "rotinas.json")


@ferramenta(
    "criar_rotina",
    "Cria ou substitui uma rotina: um nome (ex.: 'modo trabalho', 'chegando em casa') que dispara vários passos. "
    "Escreva cada passo como uma ordem curta em linguagem natural.",
    {
        "nome": {"type": "string"},
        "passos": {"type": "array", "items": {"type": "string"}, "description": "Ex.: ['abrir o Spotify', 'volume em 30']"},
    },
    ["nome", "passos"],
)
def criar_rotina(nome: str, passos: list[str]) -> str:
    rotinas.salvar(nome, passos)
    return f"Rotina '{nome}' salva com {len(passos)} passo(s)."


@ferramenta("listar_rotinas", "Lista as rotinas salvas e os passos de cada uma.")
def listar_rotinas() -> str:
    todas = rotinas.todas()
    if not todas:
        return "Nenhuma rotina salva."
    return "\n".join(f"{nome}: " + "; ".join(passos) for nome, passos in todas.items())


@ferramenta(
    "executar_rotina",
    "Busca os passos de uma rotina salva. Depois de chamar, EXECUTE os passos em ordem com suas ferramentas.",
    {"nome": {"type": "string"}},
    ["nome"],
)
def executar_rotina(nome: str) -> str:
    achada = rotinas.achar(nome)
    if not achada:
        return f"Não existe rotina chamada '{nome}'. Rotinas salvas: {', '.join(rotinas.nomes()) or 'nenhuma'}."
    nome_real, passos = achada
    lista = "\n".join(f"{i}. {p}" for i, p in enumerate(passos, 1))
    return (
        f"Rotina '{nome_real}'. Execute AGORA, em ordem, cada passo com suas ferramentas "
        f"(sem pedir confirmação extra) e no final dê um resumo curto:\n{lista}"
    )


@ferramenta(
    "apagar_rotina",
    "Apaga uma rotina salva.",
    {"nome": {"type": "string"}},
    ["nome"],
)
def apagar_rotina(nome: str) -> str:
    apagada = rotinas.apagar(nome)
    return f"Rotina '{apagada}' apagada." if apagada else "Não encontrei essa rotina."
