"""Preferências que o usuário muda pela tela (voz, velocidade, tom).

Ficam em dados/preferencias.json e têm prioridade sobre o .env.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from jarvis.config import config

ARQUIVO = config.pasta_dados / "preferencias.json"
_trava = threading.Lock()

PADROES: dict[str, Any] = {
    "voz": config.voz,
    "velocidade": config.voz_velocidade,  # porcentagem, ex.: 6 -> "+6%"
    "tom": config.voz_tom,  # Hz, ex.: -3 -> "-3Hz"
}


def carregar() -> dict[str, Any]:
    dados = dict(PADROES)
    try:
        dados.update(json.loads(ARQUIVO.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return dados


def salvar(novas: dict[str, Any]) -> dict[str, Any]:
    """Valida e salva só as chaves conhecidas. Devolve as preferências completas."""
    with _trava:
        atuais = carregar()
        if "voz" in novas:
            voz = str(novas["voz"]).strip()
            if not re.fullmatch(r"[A-Za-z]{2,3}-[A-Za-z0-9]{2,4}-[A-Za-z0-9]+", voz):
                raise ValueError(f"Nome de voz inválido: {voz}")
            atuais["voz"] = voz
        if "velocidade" in novas:
            atuais["velocidade"] = max(-50, min(50, int(novas["velocidade"])))
        if "tom" in novas:
            atuais["tom"] = max(-30, min(30, int(novas["tom"])))
        ARQUIVO.write_text(json.dumps(atuais, ensure_ascii=False, indent=2), encoding="utf-8")
        return atuais


def prosodia() -> tuple[str, str, str]:
    """(voz, rate, pitch) no formato do edge-tts."""
    p = carregar()
    return p["voz"], f"{int(p['velocidade']):+d}%", f"{int(p['tom']):+d}Hz"
