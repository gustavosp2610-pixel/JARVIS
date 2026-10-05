"""Texto -> fala com vozes neurais da Microsoft (edge-tts, grátis).

A fala sai frase por frase: enquanto uma frase toca, a próxima já está sendo
gerada, o que reduz a espera e deixa a entonação mais natural. Se a voz neural
falhar, o motivo fica em `ultimo_erro` e cai para pyttsx3 (offline, mais robótica).
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from jarvis import preferencias

_trava = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2)
ultimo_erro: str | None = None

_TROCAS = [
    (re.compile(r"https?://\S+"), "o link na tela"),
    (re.compile(r"```.*?```", re.S), " o código está na tela. "),
    (re.compile(r"R\$\s?(\d[\d.,]*)"), r"\1 reais"),
    (re.compile(r"(\d)\s?%"), r"\1 por cento"),
    (re.compile(r"\bkm/h\b"), "quilômetros por hora"),
    (re.compile(r"(\d)\s?°C"), r"\1 graus"),
    (re.compile(r"[*_#`>|~]"), ""),
    (re.compile(r"^\s*[-•]\s+", re.M), ""),
    (re.compile(r"\s+"), " "),
]


def preparar_para_fala(texto: str, limite: int = 900) -> str:
    """Remove o que não deve ser lido em voz alta e encurta respostas muito longas."""
    for padrao, troca in _TROCAS:
        texto = padrao.sub(troca, texto)
    texto = texto.strip()
    if len(texto) > limite:
        corte = texto[:limite].rfind(". ")
        texto = texto[: corte + 1 if corte > limite // 3 else limite] + " O resto está na tela, senhor."
    return texto


def dividir_frases(texto: str, minimo: int = 40) -> list[str]:
    """Divide em frases, juntando as muito curtas para não picotar a fala."""
    partes = [p.strip() for p in re.split(r"(?<=[.!?…;:])\s+", texto) if p.strip()]
    frases: list[str] = []
    for p in partes:
        if frases and len(frases[-1]) < minimo:
            frases[-1] += " " + p
        else:
            frases.append(p)
    return frases


def sintetizar(texto: str) -> bytes:
    """Gera MP3 com a voz e a prosódia escolhidas pelo usuário."""
    import edge_tts

    voz, rate, pitch = preferencias.prosodia()

    async def gerar() -> bytes:
        audio = b""
        async for parte in edge_tts.Communicate(texto, voz, rate=rate, pitch=pitch).stream():
            if parte["type"] == "audio":
                audio += parte["data"]
        return audio

    audio = asyncio.run(gerar())
    if not audio:
        raise RuntimeError("o serviço de voz não devolveu áudio")
    return audio


async def _listar() -> list[dict]:
    import edge_tts

    return await edge_tts.list_voices()


def listar_vozes() -> list[dict]:
    """Vozes em português e as multilíngues (que também falam português)."""
    vozes = []
    for v in asyncio.run(_listar()):
        nome = v["ShortName"]
        if nome.startswith("pt-") or "Multilingual" in nome:
            vozes.append(
                {
                    "id": nome,
                    "nome": nome.split("-", 2)[-1].replace("Neural", "").replace("Multilingual", " Multilíngue"),
                    "idioma": v.get("Locale", ""),
                    "genero": "masculina" if v.get("Gender") == "Male" else "feminina",
                }
            )
    vozes.sort(key=lambda v: (not v["idioma"].startswith("pt-BR"), not v["idioma"].startswith("pt"), v["id"]))
    return vozes


def _tocar_mp3(audio: bytes) -> None:
    import pygame

    fd, caminho = tempfile.mkstemp(suffix=".mp3")
    with os.fdopen(fd, "wb") as f:
        f.write(audio)
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(caminho)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(40)
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
    global ultimo_erro
    texto = preparar_para_fala(texto)
    if not texto:
        return
    with _trava:  # evita duas falas ao mesmo tempo (ex.: lembrete + resposta)
        frases = dividir_frases(texto)
        try:
            proxima: Future = _executor.submit(sintetizar, frases[0])
            for i in range(len(frases)):
                audio = proxima.result()
                if i + 1 < len(frases):
                    proxima = _executor.submit(sintetizar, frases[i + 1])
                _tocar_mp3(audio)
            ultimo_erro = None
            return
        except Exception as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
        try:
            _falar_offline(texto)
        except Exception:
            pass  # sem voz disponível: o texto já aparece na tela


def testar_voz() -> str | None:
    """Fala uma frase de teste. Devolve None se a voz neural funcionou, ou o erro."""
    try:
        audio = sintetizar("Sistemas de voz online. Às suas ordens, senhor.")
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    try:
        _tocar_mp3(audio)
    except Exception as e:
        return f"A voz foi gerada, mas não consegui tocar o áudio: {type(e).__name__}: {e}"
    return None
