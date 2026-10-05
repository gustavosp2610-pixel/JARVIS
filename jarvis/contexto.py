"""Contexto que vai junto das mensagens do usuário (data/hora, memórias, rotinas).

Fica fora do system prompt para não invalidar o cache de prompt a cada minuto.
"""

from __future__ import annotations

from datetime import datetime

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def agora_texto() -> str:
    a = datetime.now().astimezone()
    return f"{_DIAS[a.weekday()]}, {a:%d/%m/%Y %H:%M} (fuso {a:%z})"


def contexto_usuario(primeira_mensagem: bool) -> str:
    """Cabeçalho da mensagem: sempre a hora; na 1ª mensagem da conversa, memórias e rotinas."""
    contexto = f"[Agora: {agora_texto()}]"
    if primeira_mensagem:
        from jarvis.memory import memoria
        from jarvis.rotinas import rotinas

        fatos = memoria.fatos()
        if fatos:
            contexto += "\n[O que você lembra sobre o usuário:\n" + "\n".join(f"- {f}" for f in fatos) + "]"
        nomes = rotinas.nomes()
        if nomes:
            contexto += (
                "\n[Rotinas salvas (se o usuário disser o nome de uma, use executar_rotina): "
                + ", ".join(nomes) + "]"
            )
    return contexto
