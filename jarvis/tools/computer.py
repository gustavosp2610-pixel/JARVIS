"""Ferramentas para controlar o computador (focadas em Windows).

Os imports de bibliotecas específicas ficam dentro das funções para o JARVIS
abrir mesmo se alguma biblioteca opcional não estiver instalada.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

from jarvis.tools import CONFIRMAR, ferramenta

WINDOWS = sys.platform == "win32"
HOME = Path.home()
LIMITE_LEITURA = 20_000  # caracteres devolvidos ao Claude ao ler arquivos

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------

_APELIDOS_PASTAS = {
    "desktop": "Desktop",
    "área de trabalho": "Desktop",
    "area de trabalho": "Desktop",
    "documentos": "Documents",
    "documents": "Documents",
    "downloads": "Downloads",
    "imagens": "Pictures",
    "fotos": "Pictures",
    "pictures": "Pictures",
    "músicas": "Music",
    "musicas": "Music",
    "music": "Music",
    "vídeos": "Videos",
    "videos": "Videos",
}


def _pastas_permitidas() -> list[Path]:
    extras = os.getenv("JARVIS_PASTAS_PERMITIDAS", "")
    pastas = [HOME] + [Path(p.strip()).expanduser() for p in extras.split(";") if p.strip()]
    return [p.resolve() for p in pastas]


def resolver_caminho(caminho: str) -> Path:
    """Converte 'downloads/x.txt', '~/x' ou caminho absoluto em Path dentro das pastas permitidas."""
    texto = caminho.strip().strip('"')
    primeiro, _, resto = texto.replace("\\", "/").partition("/")
    apelido = _APELIDOS_PASTAS.get(primeiro.lower())
    if apelido:
        base = HOME / apelido
        onedrive = HOME / "OneDrive" / apelido
        if not base.exists() and onedrive.exists():
            base = onedrive
        p = base / resto if resto else base
    else:
        p = Path(texto).expanduser()
        if not p.is_absolute():
            p = HOME / p
    p = p.resolve()
    if not any(p == base or p.is_relative_to(base) for base in _pastas_permitidas()):
        raise PermissionError(
            f"Acesso negado a {p}. Só tenho permissão para a pasta do usuário "
            "(e pastas extras em JARVIS_PASTAS_PERMITIDAS)."
        )
    return p


# ---------------------------------------------------------------------------
# Programas e sites
# ---------------------------------------------------------------------------

_PROGRAMAS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "navegador": "msedge",
    "firefox": "firefox",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador": "explorer",
    "explorador de arquivos": "explorer",
    "arquivos": "explorer",
    "paint": "mspaint",
    "cmd": "cmd",
    "prompt de comando": "cmd",
    "terminal": "wt",
    "powershell": "powershell",
    "configurações": "ms-settings:",
    "configuracoes": "ms-settings:",
    "gerenciador de tarefas": "taskmgr",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "discord": "discord:",
    "steam": "steam:",
    "teams": "msteams:",
}


def _atalhos_menu_iniciar() -> list[Path]:
    pastas = [
        Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.getenv("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    atalhos: list[Path] = []
    for pasta in pastas:
        if pasta.is_dir():
            atalhos.extend(pasta.rglob("*.lnk"))
    return atalhos


def _abrir(alvo: str) -> None:
    if WINDOWS:
        os.startfile(alvo)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", alvo])
    else:
        subprocess.Popen(["xdg-open", alvo])


@ferramenta(
    "abrir_programa",
    "Abre um programa ou aplicativo do computador pelo nome (ex.: chrome, spotify, calculadora, word).",
    {"nome": {"type": "string", "description": "Nome do programa."}},
    ["nome"],
)
def abrir_programa(nome: str) -> str:
    chave = nome.strip().lower()
    alvo = _PROGRAMAS.get(chave)
    if alvo is None and WINDOWS:
        # Procura um atalho no Menu Iniciar cujo nome contenha o pedido.
        for atalho in _atalhos_menu_iniciar():
            if chave in atalho.stem.lower():
                alvo = str(atalho)
                break
    if alvo is None:
        alvo = shutil.which(chave) or chave
    try:
        _abrir(alvo)
    except OSError as e:
        return f"Não consegui abrir '{nome}': {e}"
    return f"Abrindo {nome}."


@ferramenta(
    "fechar_programa",
    "Fecha um programa em execução pelo nome do processo (ex.: chrome, notepad, spotify).",
    {"nome": {"type": "string", "description": "Nome do processo, sem .exe."}},
    ["nome"],
    risco=CONFIRMAR,
)
def fechar_programa(nome: str) -> str:
    import psutil

    alvo = nome.strip().lower().removesuffix(".exe")
    fechados = 0
    for proc in psutil.process_iter(["name"]):
        nome_proc = (proc.info.get("name") or "").lower().removesuffix(".exe")
        if nome_proc == alvo:
            try:
                proc.terminate()
                fechados += 1
            except psutil.Error:
                pass
    return f"{fechados} processo(s) de {nome} fechado(s)." if fechados else f"{nome} não está aberto."


@ferramenta(
    "abrir_site",
    "Abre um site no navegador padrão.",
    {"url": {"type": "string", "description": "Endereço do site, ex.: youtube.com"}},
    ["url"],
)
def abrir_site(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"Abrindo {url}."


@ferramenta(
    "pesquisar_no_navegador",
    "Abre uma pesquisa do Google no navegador para o usuário ver os resultados na tela.",
    {"termo": {"type": "string"}},
    ["termo"],
)
def pesquisar_no_navegador(termo: str) -> str:
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(termo))
    return f"Pesquisa por '{termo}' aberta no navegador."


@ferramenta(
    "tocar_no_youtube",
    "Toca no YouTube o primeiro vídeo encontrado para a busca (músicas, clipes, vídeos).",
    {"busca": {"type": "string", "description": "O que tocar, ex.: 'AC/DC Back in Black'."}},
    ["busca"],
)
def tocar_no_youtube(busca: str) -> str:
    url_busca = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(busca)
    try:
        req = urllib.request.Request(url_busca, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        achado = re.search(r'"videoId":"([\w-]{11})"', html)
    except OSError:
        achado = None
    if achado:
        webbrowser.open(f"https://www.youtube.com/watch?v={achado.group(1)}")
        return f"Tocando '{busca}' no YouTube."
    webbrowser.open(url_busca)
    return f"Abri a busca por '{busca}' no YouTube."


# ---------------------------------------------------------------------------
# Volume e mídia (teclas multimídia virtuais do Windows — sem dependências)
# ---------------------------------------------------------------------------

_VK = {
    "mudo": 0xAD,
    "diminuir": 0xAE,
    "aumentar": 0xAF,
    "proxima": 0xB0,
    "anterior": 0xB1,
    "parar": 0xB2,
    "tocar_pausar": 0xB3,
}


def _tecla(vk: int, vezes: int = 1) -> None:
    if not WINDOWS:
        raise OSError("Controle de mídia disponível só no Windows.")
    import ctypes

    for _ in range(vezes):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)  # type: ignore[attr-defined]
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # type: ignore[attr-defined]
        time.sleep(0.01)


@ferramenta(
    "controlar_volume",
    "Controla o volume do computador. 'definir' ajusta para um nível exato de 0 a 100.",
    {
        "acao": {"type": "string", "enum": ["aumentar", "diminuir", "mudo", "definir"]},
        "nivel": {"type": "integer", "description": "Para 'definir': 0 a 100. Para aumentar/diminuir: quantos pontos (padrão 10)."},
    },
    ["acao"],
)
def controlar_volume(acao: str, nivel: int | None = None) -> str:
    try:
        if acao == "mudo":
            _tecla(_VK["mudo"])
            return "Som mudo alternado."
        if acao == "definir":
            nivel = max(0, min(100, nivel if nivel is not None else 50))
            _tecla(_VK["diminuir"], 50)  # cada toque = 2 pontos
            _tecla(_VK["aumentar"], nivel // 2)
            return f"Volume em {nivel}%."
        passos = max(1, (nivel or 10) // 2)
        _tecla(_VK[acao], passos)
        return f"Volume: {acao}."
    except (OSError, KeyError) as e:
        return f"Não consegui ajustar o volume: {e}"


@ferramenta(
    "controlar_midia",
    "Controla a música/vídeo tocando agora (Spotify, YouTube, etc.).",
    {"acao": {"type": "string", "enum": ["tocar_pausar", "proxima", "anterior", "parar"]}},
    ["acao"],
)
def controlar_midia(acao: str) -> str:
    try:
        _tecla(_VK[acao])
    except (OSError, KeyError) as e:
        return f"Não consegui controlar a mídia: {e}"
    return f"Mídia: {acao.replace('_', '/')}."


# ---------------------------------------------------------------------------
# Sistema
# ---------------------------------------------------------------------------


@ferramenta("info_sistema", "Mostra bateria, uso de CPU, memória RAM e espaço em disco.")
def info_sistema() -> dict:
    import psutil

    info: dict = {
        "sistema": f"{platform.system()} {platform.release()}",
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": psutil.virtual_memory().percent,
        "disco_livre_gb": round(shutil.disk_usage(HOME.anchor or "/").free / 1e9, 1),
        "disco_total_gb": round(shutil.disk_usage(HOME.anchor or "/").total / 1e9, 1),
    }
    bateria = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bateria:
        info["bateria_percent"] = round(bateria.percent)
        info["carregando"] = bateria.power_plugged
    return info


@ferramenta("tirar_print", "Tira um print (captura) da tela e salva na pasta Imagens/JARVIS.")
def tirar_print() -> str:
    from PIL import ImageGrab

    pasta = HOME / "Pictures" / "JARVIS"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"print_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    ImageGrab.grab(all_screens=True).save(arquivo)
    return f"Print salvo em {arquivo}."


@ferramenta("bloquear_pc", "Bloqueia a tela do computador.")
def bloquear_pc() -> str:
    if not WINDOWS:
        return "Bloqueio disponível só no Windows."
    import ctypes

    ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
    return "Tela bloqueada."


@ferramenta(
    "energia_pc",
    "Desliga, reinicia, hiberna ou cancela um desligamento agendado do computador.",
    {
        "acao": {"type": "string", "enum": ["desligar", "reiniciar", "hibernar", "cancelar"]},
        "em_minutos": {"type": "integer", "description": "Atraso em minutos (padrão 1)."},
    },
    ["acao"],
    risco=CONFIRMAR,
)
def energia_pc(acao: str, em_minutos: int | None = None) -> str:
    if not WINDOWS:
        return "Controle de energia disponível só no Windows."
    segundos = str(max(0, (em_minutos if em_minutos is not None else 1) * 60))
    comandos = {
        "desligar": ["shutdown", "/s", "/t", segundos],
        "reiniciar": ["shutdown", "/r", "/t", segundos],
        "hibernar": ["shutdown", "/h"],
        "cancelar": ["shutdown", "/a"],
    }
    subprocess.run(comandos[acao], check=False)
    return f"Comando '{acao}' enviado."


@ferramenta(
    "executar_comando",
    "Executa um comando do PowerShell no computador e devolve a saída. Use só quando nenhuma outra ferramenta resolver.",
    {"comando": {"type": "string"}},
    ["comando"],
    risco=CONFIRMAR,
)
def executar_comando(comando: str) -> str:
    shell = ["powershell", "-NoProfile", "-Command", comando] if WINDOWS else ["bash", "-c", comando]
    try:
        r = subprocess.run(shell, capture_output=True, text=True, timeout=60, cwd=HOME)
    except subprocess.TimeoutExpired:
        return "O comando passou de 60 segundos e foi interrompido."
    saida = (r.stdout + ("\n" + r.stderr if r.stderr else "")).strip()
    return f"Código de saída {r.returncode}.\n{saida[:LIMITE_LEITURA]}"


# ---------------------------------------------------------------------------
# Área de transferência
# ---------------------------------------------------------------------------


@ferramenta(
    "copiar_texto",
    "Copia um texto para a área de transferência (Ctrl+V cola depois).",
    {"texto": {"type": "string"}},
    ["texto"],
)
def copiar_texto(texto: str) -> str:
    import pyperclip

    pyperclip.copy(texto)
    return "Texto copiado."


@ferramenta("ler_area_de_transferencia", "Lê o texto que está copiado na área de transferência.")
def ler_area_de_transferencia() -> str:
    import pyperclip

    return pyperclip.paste()[:LIMITE_LEITURA] or "A área de transferência está vazia."


# ---------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------


@ferramenta(
    "listar_arquivos",
    "Lista arquivos e pastas de uma pasta (aceita apelidos: downloads, documentos, área de trabalho, imagens...).",
    {"pasta": {"type": "string"}},
    ["pasta"],
)
def listar_arquivos(pasta: str) -> str:
    p = resolver_caminho(pasta)
    if not p.is_dir():
        return f"{p} não é uma pasta."
    itens = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:100]
    linhas = [f"{'[pasta] ' if i.is_dir() else ''}{i.name}" for i in itens]
    return f"{p} (mais recentes primeiro):\n" + "\n".join(linhas) if linhas else f"{p} está vazia."


@ferramenta(
    "procurar_arquivos",
    "Procura arquivos pelo nome (ou parte dele) dentro de uma pasta e subpastas.",
    {
        "nome": {"type": "string", "description": "Parte do nome, ex.: 'curriculo' ou '.pdf'."},
        "pasta": {"type": "string", "description": "Onde procurar (padrão: pasta do usuário)."},
    },
    ["nome"],
)
def procurar_arquivos(nome: str, pasta: str | None = None) -> str:
    base = resolver_caminho(pasta or str(HOME))
    alvo = nome.lower()
    achados: list[str] = []
    for raiz, dirs, arquivos in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"AppData", "node_modules"}]
        for a in arquivos:
            if alvo in a.lower():
                achados.append(str(Path(raiz) / a))
                if len(achados) >= 50:
                    return "\n".join(achados) + "\n(parei em 50 resultados)"
    return "\n".join(achados) if achados else "Nada encontrado."


@ferramenta(
    "abrir_arquivo",
    "Abre um arquivo ou pasta com o programa padrão do Windows.",
    {"caminho": {"type": "string"}},
    ["caminho"],
)
def abrir_arquivo(caminho: str) -> str:
    p = resolver_caminho(caminho)
    if not p.exists():
        return f"{p} não existe."
    _abrir(str(p))
    return f"Abrindo {p.name}."


@ferramenta(
    "ler_arquivo_texto",
    "Lê o conteúdo de um arquivo de texto (txt, md, csv, código...).",
    {"caminho": {"type": "string"}},
    ["caminho"],
)
def ler_arquivo_texto(caminho: str) -> str:
    p = resolver_caminho(caminho)
    if not p.is_file():
        return f"{p} não é um arquivo."
    texto = p.read_text(encoding="utf-8", errors="replace")
    if len(texto) > LIMITE_LEITURA:
        return texto[:LIMITE_LEITURA] + f"\n[... cortado; arquivo tem {len(texto)} caracteres]"
    return texto


@ferramenta(
    "escrever_arquivo",
    "Cria ou substitui um arquivo de texto com o conteúdo informado (ex.: notas, listas).",
    {"caminho": {"type": "string"}, "conteudo": {"type": "string"}},
    ["caminho", "conteudo"],
    risco=CONFIRMAR,
)
def escrever_arquivo(caminho: str, conteudo: str) -> str:
    p = resolver_caminho(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
    return f"Arquivo salvo em {p}."


@ferramenta(
    "mover_arquivo",
    "Move ou renomeia um arquivo ou pasta.",
    {"origem": {"type": "string"}, "destino": {"type": "string"}},
    ["origem", "destino"],
    risco=CONFIRMAR,
)
def mover_arquivo(origem: str, destino: str) -> str:
    o, d = resolver_caminho(origem), resolver_caminho(destino)
    if not o.exists():
        return f"{o} não existe."
    resultado = shutil.move(str(o), str(d))
    return f"Movido para {resultado}."


@ferramenta(
    "apagar_arquivo",
    "Manda um arquivo ou pasta para a Lixeira (dá para recuperar depois).",
    {"caminho": {"type": "string"}},
    ["caminho"],
    risco=CONFIRMAR,
)
def apagar_arquivo(caminho: str) -> str:
    from send2trash import send2trash

    p = resolver_caminho(caminho)
    if p in _pastas_permitidas():
        return "Não vou apagar uma pasta raiz inteira."
    if not p.exists():
        return f"{p} não existe."
    send2trash(str(p))
    return f"{p.name} foi para a Lixeira."


# ---------------------------------------------------------------------------
# Timers / lembretes (avisam por voz quando terminam)
# ---------------------------------------------------------------------------

# main.py troca isto por uma função que fala o aviso em voz alta.
avisar: Callable[[str], None] = lambda texto: print(f"\n⏰ {texto}")


@ferramenta(
    "criar_timer",
    "Cria um timer/lembrete que avisa em voz alta depois de X minutos (funciona enquanto o JARVIS estiver aberto).",
    {
        "minutos": {"type": "number"},
        "mensagem": {"type": "string", "description": "O que dizer quando o tempo acabar."},
    },
    ["minutos", "mensagem"],
)
def criar_timer(minutos: float, mensagem: str) -> str:
    t = threading.Timer(max(0.0, float(minutos)) * 60, lambda: avisar(mensagem))
    t.daemon = True
    t.start()
    return f"Timer de {minutos:g} minuto(s) criado."
