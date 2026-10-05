"""Ver a tela e usar mouse/teclado — o "computer use" do Claude.

O Claude pede ações do toolset `computer_toolset_20260801` (screenshot, left_click,
type, key...). Este módulo executa cada uma no PC de verdade com pyautogui.

As capturas são reduzidas para caber no limite de imagem do modelo (lado maior
<= 1568 px e ~1,15 megapixel); o Claude responde coordenadas nessa imagem
reduzida, e aqui elas são convertidas de volta para pixels reais da tela.
"""

from __future__ import annotations

import base64
import io
import math
import sys
import time
from typing import Any

TOOLSET = {"type": "computer_toolset_20260801"}
NAO_EXECUTADO = "Not executed: an earlier computer action in this turn failed."

# Ações que só olham a tela (não precisam de autorização).
SOMENTE_LEITURA = {"screenshot", "zoom", "cursor_position", "wait"}

LADO_MAX = 1568
PIXELS_MAX = 1_150_000

_TECLAS = {
    "return": "enter", "enter": "enter", "kp_enter": "enter",
    "escape": "esc", "esc": "esc",
    "backspace": "backspace", "delete": "delete", "tab": "tab", "space": "space",
    "super": "win", "super_l": "win", "win": "win", "windows": "win", "meta": "win", "cmd": "win",
    "control": "ctrl", "control_l": "ctrl", "ctrl": "ctrl",
    "alt": "alt", "alt_l": "alt", "shift": "shift", "shift_l": "shift",
    "page_up": "pageup", "prior": "pageup", "page_down": "pagedown", "next": "pagedown",
    "home": "home", "end": "end", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "print": "printscreen", "caps_lock": "capslock", "menu": "apps",
}


def converter_tecla(nome: str) -> str:
    n = nome.strip().lower()
    if n in _TECLAS:
        return _TECLAS[n]
    if n.startswith("f") and n[1:].isdigit():
        return n
    return n


def converter_combinacao(texto: str) -> list[str]:
    """'ctrl+shift+Escape' -> ['ctrl', 'shift', 'esc']"""
    return [converter_tecla(p) for p in texto.split("+") if p.strip()]


def calcular_escala(largura: int, altura: int) -> float:
    return min(1.0, LADO_MAX / max(largura, altura), math.sqrt(PIXELS_MAX / (largura * altura)))


class ParadaSolicitada(Exception):
    pass


class Controle:
    """Executa os membros do toolset. `pyautogui` e `grab` podem ser trocados nos testes."""

    def __init__(self, pyautogui: Any = None, grab: Any = None) -> None:
        self._pg = pyautogui
        self._grab = grab
        self.escala = 1.0
        self.tamanho_captura = (1280, 800)
        self.parar = False
        self._dpi_ok = False

    # -- dependências ---------------------------------------------------------
    @property
    def pg(self) -> Any:
        if self._pg is None:
            self._preparar_dpi()
            import pyautogui

            pyautogui.FAILSAFE = True  # mouse no canto superior esquerdo interrompe tudo
            pyautogui.PAUSE = 0.05
            self._pg = pyautogui
        return self._pg

    def _preparar_dpi(self) -> None:
        # Sem isso, em telas com zoom (125%, 150%) a captura e o mouse usam escalas diferentes.
        if self._dpi_ok or sys.platform != "win32":
            return
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._dpi_ok = True

    def _capturar(self, regiao: tuple[int, int, int, int] | None = None) -> Any:
        if self._grab is not None:
            return self._grab(regiao)
        self._preparar_dpi()
        from PIL import ImageGrab

        return ImageGrab.grab(bbox=regiao)

    # -- utilidades -----------------------------------------------------------
    def _real(self, ponto: Any) -> tuple[int, int]:
        x, y = ponto
        return round(float(x) / self.escala), round(float(y) / self.escala)

    @staticmethod
    def _imagem(img: Any) -> list[dict[str, Any]]:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        dados = base64.b64encode(buf.getvalue()).decode()
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": dados}}]

    def _checar_parada(self) -> None:
        if self.parar:
            raise ParadaSolicitada("O usuário pediu para parar.")

    @staticmethod
    def descrever(nome: str, entrada: dict[str, Any]) -> str:
        """Texto curto para o registro de operações do HUD."""
        if "coordinate" in entrada:
            x, y = entrada["coordinate"]
            return f"{nome.replace('_', ' ')} em {x}, {y}"
        if nome == "type":
            t = str(entrada.get("text", ""))
            return f"digitando “{t[:40]}{'…' if len(t) > 40 else ''}”"
        if nome in ("key", "hold_key"):
            return f"tecla {entrada.get('text', '')}"
        return nome.replace("_", " ")

    # -- ações ----------------------------------------------------------------
    def screenshot(self) -> list[dict[str, Any]]:
        img = self._capturar()
        self.escala = calcular_escala(*img.size)
        if self.escala < 1:
            img = img.resize((round(img.width * self.escala), round(img.height * self.escala)))
        self.tamanho_captura = img.size
        return self._imagem(img)

    def executar(self, nome: str, entrada: dict[str, Any]) -> str | list[dict[str, Any]]:
        self._checar_parada()
        pg = self.pg if nome not in ("screenshot", "zoom", "wait") else None
        modificadores = converter_combinacao(entrada["text"]) if entrada.get("text") and nome.endswith(("click", "scroll", "drag")) else []

        if nome == "screenshot":
            return self.screenshot()
        if nome == "zoom":
            x0, y0 = self._real(entrada["region"][:2])
            x1, y1 = self._real(entrada["region"][2:])
            img = self._capturar((min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1))
            # Cabe nas dimensões da captura normal, mantendo a proporção (ampliar ajuda a ler textos pequenos).
            lw, lh = self.tamanho_captura
            fator = min(lw / img.width, lh / img.height)
            img = img.resize((max(1, round(img.width * fator)), max(1, round(img.height * fator))))
            return self._imagem(img)
        if nome == "cursor_position":
            x, y = pg.position()
            return f"X={round(x * self.escala)}, Y={round(y * self.escala)}"
        if nome == "wait":
            fim = time.monotonic() + min(float(entrada.get("duration", 1)), 300)
            while time.monotonic() < fim:
                self._checar_parada()
                time.sleep(0.2)
            return "OK"

        cliques = {"left_click": ("left", 1), "right_click": ("right", 1), "middle_click": ("middle", 1),
                   "double_click": ("left", 2), "triple_click": ("left", 3)}
        if nome in cliques:
            botao, vezes = cliques[nome]
            alvo = self._real(entrada["coordinate"]) if entrada.get("coordinate") else pg.position()
            for m in modificadores:
                pg.keyDown(m)
            try:
                pg.click(x=alvo[0], y=alvo[1], clicks=vezes, interval=0.08, button=botao)
            finally:
                for m in reversed(modificadores):
                    pg.keyUp(m)
            return "OK"
        if nome == "mouse_move":
            pg.moveTo(*self._real(entrada["coordinate"]), duration=0.15)
            return "OK"
        if nome == "left_click_drag":
            inicio, fim = self._real(entrada["start_coordinate"]), self._real(entrada["coordinate"])
            for m in modificadores:
                pg.keyDown(m)
            try:
                pg.moveTo(*inicio)
                pg.dragTo(*fim, duration=0.4, button="left")
            finally:
                for m in reversed(modificadores):
                    pg.keyUp(m)
            return "OK"
        if nome == "left_mouse_down":
            pg.mouseDown(button="left")
            return "OK"
        if nome == "left_mouse_up":
            pg.mouseUp(button="left")
            return "OK"
        if nome == "scroll":
            if entrada.get("coordinate"):
                pg.moveTo(*self._real(entrada["coordinate"]))
            qtd = int(entrada.get("scroll_amount", 3))
            direcao = entrada.get("scroll_direction", "down")
            for m in modificadores:
                pg.keyDown(m)
            try:
                if direcao in ("up", "down"):
                    pg.scroll(qtd * 120 * (1 if direcao == "up" else -1))
                else:
                    pg.hscroll(qtd * 120 * (1 if direcao == "right" else -1))
            finally:
                for m in reversed(modificadores):
                    pg.keyUp(m)
            return "OK"
        if nome == "type":
            # Colar pela área de transferência: digita acentos e ç corretamente.
            import pyperclip

            anterior = None
            try:
                anterior = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(str(entrada["text"]))
            pg.hotkey("ctrl", "v")
            time.sleep(0.15)
            if anterior is not None:
                try:
                    pyperclip.copy(anterior)
                except Exception:
                    pass
            return "OK"
        if nome == "key":
            teclas = converter_combinacao(str(entrada["text"]))
            for _ in range(max(1, min(int(entrada.get("repeat", 1)), 100))):
                self._checar_parada()
                pg.hotkey(*teclas)
            return "OK"
        if nome == "hold_key":
            teclas = converter_combinacao(str(entrada["text"]))
            for t in teclas:
                pg.keyDown(t)
            try:
                time.sleep(min(float(entrada.get("duration", 1)), 300))
            finally:
                for t in reversed(teclas):
                    pg.keyUp(t)
            return "OK"
        raise ValueError(f"Ação de computador desconhecida: {nome}")


controle = Controle()
