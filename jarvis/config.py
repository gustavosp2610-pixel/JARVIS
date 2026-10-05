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
    modelo_gemini: str = field(default_factory=lambda: os.getenv("JARVIS_MODELO_GEMINI", "gemini-flash-latest"))
    esforco: str = field(default_factory=lambda: os.getenv("JARVIS_ESFORCO", "medium"))
    nome_usuario: str = field(default_factory=lambda: os.getenv("JARVIS_NOME_USUARIO", "senhor"))
    cidade: str = field(default_factory=lambda: os.getenv("JARVIS_CIDADE", ""))
    palavra_ativacao: str = field(default_factory=lambda: os.getenv("JARVIS_PALAVRA_ATIVACAO", "jarvis"))
    voz: str = field(default_factory=lambda: os.getenv("JARVIS_VOZ", "pt-BR-AntonioNeural"))
    voz_velocidade: int = field(default_factory=lambda: int(os.getenv("JARVIS_VOZ_VELOCIDADE", "6")))
    voz_tom: int = field(default_factory=lambda: int(os.getenv("JARVIS_VOZ_TOM", "-3")))
    idioma: str = field(default_factory=lambda: os.getenv("JARVIS_IDIOMA", "pt-BR"))
    controle_pc: bool = field(default_factory=lambda: _bool(os.getenv("JARVIS_CONTROLE_PC"), True))
    whatsapp_enviar_sozinho: bool = field(
        default_factory=lambda: _bool(os.getenv("JARVIS_WHATSAPP_ENVIAR_SOZINHO"), True)
    )
    pesquisa_web: bool = field(default_factory=lambda: _bool(os.getenv("JARVIS_PESQUISA_WEB"), True))
    pasta_dados: Path = field(default_factory=lambda: Path(os.getenv("JARVIS_PASTA_DADOS", str(RAIZ / "dados"))))

    @property
    def ia(self) -> str:
        """Qual cérebro usar: 'gemini' (grátis) ou 'claude' (pago por uso)."""
        escolhida = os.getenv("JARVIS_IA", "").strip().lower()
        if escolhida in ("gemini", "claude"):
            return escolhida
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return "gemini"
        return "claude"

    @property
    def modelo_ativo(self) -> str:
        return self.modelo_gemini if self.ia == "gemini" else self.modelo

    def __post_init__(self) -> None:
        self.pasta_dados.mkdir(parents=True, exist_ok=True)


config = Config()
