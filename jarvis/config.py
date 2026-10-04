"""Configurações lidas do arquivo .env (veja .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _bool(valor: str | None, padrao: bool) -> bool:
    if valor is None or valor == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "s"}


@dataclass
class Config:
    modelo: str = field(default_factory=lambda: os.getenv("JARVIS_MODELO", "claude-opus-5-5"))
    esforco: str = field(default_factory=lambda: os.getenv("JARVIS_ESFORCO", "low"))
    nome_usuario: str = field(default_factory=lambda: os.getenv("JARVIS_NOME_USUARIO", "senhor"))
    cidade: str = field(default_factory=lambda: os.getenv("JARVIS_CIDADE", ""))
    palavra_ativacao: str = field(default_factory=lambda: os.getenv("JARVIS_PALAVRA_ATIVACAO", "jarvis"))
    voz: str = field(default_factory=lambda: os.getenv("JARVIS_VOZ", "pt-BR-AntonioNeural"))
    idioma: str = field(default_factory=lambda: os.getenv("JARVIS_IDIOMA", "pt-BR"))
    pesquisa_web: bool = field(default_factory=lambda: _bool(os.getenv("JARVIS_PESQUISA_WEB"), True))
    pasta_dados: Path = field(default_factory=lambda: Path(os.getenv("JARVIS_PASTA_DADOS", str(RAIZ / "dados"))))

    def __post_init__(self) -> None:
        self.pasta_dados.mkdir(parents=True, exist_ok=True)


config = Config()
