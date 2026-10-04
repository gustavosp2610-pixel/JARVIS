"""Memória de longo prazo simples: uma lista de fatos salva em JSON."""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.config import config
from jarvis.tools import ferramenta


class Memoria:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo

    def fatos(self) -> list[str]:
        if not self.arquivo.exists():
            return []
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [str(f) for f in dados.get("fatos", [])]

    def _salvar(self, fatos: list[str]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(
            json.dumps({"fatos": fatos}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def lembrar(self, fato: str) -> str:
        fato = fato.strip()
        fatos = self.fatos()
        if fato.lower() in (f.lower() for f in fatos):
            return "Já estava na memória."
        fatos.append(fato)
        self._salvar(fatos)
        return f"Memorizado: {fato}"

    def esquecer(self, trecho: str) -> str:
        fatos = self.fatos()
        restantes = [f for f in fatos if trecho.lower() not in f.lower()]
        removidos = len(fatos) - len(restantes)
        if removidos == 0:
            return "Nenhuma memória correspondente encontrada."
        self._salvar(restantes)
        return f"{removidos} memória(s) apagada(s)."


memoria = Memoria(config.pasta_dados / "memoria.json")


@ferramenta(
    "lembrar",
    "Guarda permanentemente um fato sobre o usuário (preferência, rotina, nome de alguém, etc.).",
    {"fato": {"type": "string", "description": "O fato, numa frase curta e autoexplicativa."}},
    ["fato"],
)
def lembrar(fato: str) -> str:
    return memoria.lembrar(fato)


@ferramenta(
    "esquecer",
    "Apaga memórias que contenham o trecho informado.",
    {"trecho": {"type": "string", "description": "Palavra ou trecho da memória a apagar."}},
    ["trecho"],
)
def esquecer(trecho: str) -> str:
    return memoria.esquecer(trecho)


@ferramenta("listar_memorias", "Lista tudo o que o JARVIS lembra sobre o usuário.")
def listar_memorias() -> str:
    fatos = memoria.fatos()
    return "\n".join(f"- {f}" for f in fatos) if fatos else "Nenhuma memória salva."
