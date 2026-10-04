"""Microfone -> texto, com palavra de ativação ("Jarvis")."""

from __future__ import annotations

import unicodedata

from jarvis.config import config


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


# Formas como o reconhecedor costuma escrever "Jarvis" em português.
_VARIACOES = {"jarvis", "jarvas", "javis", "jarves", "djarvis", "jervis", "jarbas"}


def extrair_comando(frase: str, palavra: str | None = None) -> str | None:
    """Se a frase contém a palavra de ativação, devolve o que vem depois dela.

    Retorna "" se disse só "Jarvis", e None se a palavra não apareceu.
    """
    palavras_ativacao = {_normalizar(palavra or config.palavra_ativacao)} | _VARIACOES
    tokens = frase.split()
    for i, token in enumerate(tokens):
        if _normalizar(token).strip(",.!?;:") in palavras_ativacao:
            return " ".join(tokens[i + 1 :]).strip(" ,.!?;:")
    return None


class Ouvinte:
    def __init__(self) -> None:
        import speech_recognition as sr

        self.sr = sr
        self.reconhecedor = sr.Recognizer()
        self.reconhecedor.pause_threshold = 0.8
        self.reconhecedor.dynamic_energy_threshold = True
        self.microfone = sr.Microphone()
        with self.microfone as fonte:
            self.reconhecedor.adjust_for_ambient_noise(fonte, duration=1)

    def ouvir(self, espera: float | None = None, tempo_max: float = 15) -> str | None:
        """Escuta uma frase e devolve o texto (ou None se não entendeu/silêncio).

        espera: segundos aguardando alguém começar a falar (None = para sempre).
        """
        sr = self.sr
        with self.microfone as fonte:
            try:
                audio = self.reconhecedor.listen(fonte, timeout=espera, phrase_time_limit=tempo_max)
            except sr.WaitTimeoutError:
                return None
        try:
            return self.reconhecedor.recognize_google(audio, language=config.idioma)
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            return None
