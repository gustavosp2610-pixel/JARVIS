"""Texto -> fala. Usa vozes neurais do Edge (grátis, online); cai para pyttsx3 (offline)."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading

from jarvis.config import config

_trava = threading.Lock()


def _limpar(texto: str) -> str:
    texto = re.sub(r"https?://\S+", "o link", texto)
    texto = re.sub(r"[*_#`>|]", "", texto)
    return texto.strip()


def _falar_edge(texto: str) -> None:
    import edge_tts
    import pygame

    fd, caminho = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(texto, config.voz).save(caminho))
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(caminho)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        pygame.mixer.music.unload()
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass


def _falar_offline(texto: str) -> None:
    import pyttsx3

    motor = pyttsx3.init()
    for voz in motor.getProperty("voices"):
        if "pt" in (voz.id + str(getattr(voz, "languages", ""))).lower():
            motor.setProperty("voice", voz.id)
            break
    motor.say(texto)
    motor.runAndWait()


def falar(texto: str) -> None:
    texto = _limpar(texto)
    if not texto:
        return
    with _trava:  # evita duas falas ao mesmo tempo (ex.: timer + resposta)
        try:
            _falar_edge(texto)
        except Exception:
            try:
                _falar_offline(texto)
            except Exception:
                pass  # sem voz disponível: o texto já aparece na tela
