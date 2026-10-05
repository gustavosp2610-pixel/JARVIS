"""Organizar o PC: analisar pastas, achar arquivos grandes, arrumar Downloads, limpar temporários."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from jarvis.tools import CONFIRMAR, ferramenta
from jarvis.tools.computer import resolver_caminho

CATEGORIAS: dict[str, set[str]] = {
    "Imagens": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".ico", ".tif", ".tiff"},
    "Documentos": {".pdf", ".doc", ".docx", ".txt", ".md", ".odt", ".rtf", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".epub"},
    "Vídeos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"},
    "Músicas": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Compactados": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Instaladores": {".exe", ".msi", ".msix", ".appx", ".iso", ".apk"},
}


def categoria_de(arquivo: Path) -> str:
    sufixo = arquivo.suffix.lower()
    for nome, extensoes in CATEGORIAS.items():
        if sufixo in extensoes:
            return nome
    return "Outros"


def _tamanho(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} GB"


def _arquivos_soltos(pasta: Path) -> list[Path]:
    return [a for a in pasta.iterdir() if a.is_file() and not a.name.startswith(".") and a.suffix.lower() not in {".tmp", ".crdownload", ".part"}]


def _destino_livre(destino: Path) -> Path:
    """Nunca sobrescreve: 'foto.jpg' -> 'foto (2).jpg' se já existir."""
    if not destino.exists():
        return destino
    i = 2
    while True:
        candidato = destino.with_name(f"{destino.stem} ({i}){destino.suffix}")
        if not candidato.exists():
            return candidato
        i += 1


@ferramenta(
    "analisar_pasta",
    "Mostra o tamanho total de uma pasta, quantos arquivos de cada tipo e os maiores arquivos.",
    {"pasta": {"type": "string", "description": "Ex.: downloads, documentos, área de trabalho."}},
    ["pasta"],
)
def analisar_pasta(pasta: str) -> str:
    base = resolver_caminho(pasta)
    if not base.is_dir():
        return f"{base} não é uma pasta."
    total, tipos, maiores = 0, Counter(), []
    for raiz, dirs, arquivos in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "AppData"]
        for nome in arquivos:
            caminho = Path(raiz) / nome
            try:
                tam = caminho.stat().st_size
            except OSError:
                continue
            total += tam
            tipos[categoria_de(caminho)] += 1
            maiores.append((tam, caminho))
    maiores.sort(reverse=True)
    linhas = [f"{base}: {_tamanho(total)} em {sum(tipos.values())} arquivos."]
    linhas.append("Por tipo: " + ", ".join(f"{t} {n}" for t, n in tipos.most_common()))
    linhas.append("Maiores:")
    linhas += [f"- {_tamanho(t)}  {c.relative_to(base)}" for t, c in maiores[:10]]
    return "\n".join(linhas)


@ferramenta(
    "arquivos_grandes",
    "Lista os arquivos maiores que X MB numa pasta (padrão: toda a pasta do usuário), para liberar espaço.",
    {"pasta": {"type": "string"}, "minimo_mb": {"type": "integer", "description": "Padrão 100."}},
)
def arquivos_grandes(pasta: str | None = None, minimo_mb: int | None = None) -> str:
    base = resolver_caminho(pasta or "~")
    limite = max(1, int(minimo_mb or 100)) * 1024 * 1024
    achados = []
    for raiz, dirs, arquivos in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"AppData", "node_modules"}]
        for nome in arquivos:
            caminho = Path(raiz) / nome
            try:
                tam = caminho.stat().st_size
            except OSError:
                continue
            if tam >= limite:
                achados.append((tam, caminho))
    achados.sort(reverse=True)
    if not achados:
        return f"Nenhum arquivo acima de {limite // 1024 // 1024} MB em {base}."
    return "\n".join(f"- {_tamanho(t)}  {c}" for t, c in achados[:30])


def plano_organizacao(base: Path) -> dict[str, list[Path]]:
    plano: dict[str, list[Path]] = {}
    for arquivo in _arquivos_soltos(base):
        plano.setdefault(categoria_de(arquivo), []).append(arquivo)
    return plano


@ferramenta(
    "planejar_organizacao",
    "Mostra (sem mexer em nada) como os arquivos soltos de uma pasta seriam separados em subpastas por tipo.",
    {"pasta": {"type": "string"}},
    ["pasta"],
)
def planejar_organizacao(pasta: str) -> str:
    base = resolver_caminho(pasta)
    plano = plano_organizacao(base)
    if not plano:
        return f"Não há arquivos soltos em {base}."
    linhas = [f"Plano para {base} ({sum(len(v) for v in plano.values())} arquivos):"]
    for cat, arquivos in sorted(plano.items()):
        exemplos = ", ".join(a.name for a in arquivos[:3]) + ("…" if len(arquivos) > 3 else "")
        linhas.append(f"- {cat}: {len(arquivos)} ({exemplos})")
    return "\n".join(linhas)


@ferramenta(
    "organizar_pasta",
    "Organiza os arquivos soltos de uma pasta em subpastas por tipo (Imagens, Documentos, Vídeos, Músicas, "
    "Compactados, Instaladores, Outros). Não mexe em subpastas existentes e nunca sobrescreve arquivos.",
    {"pasta": {"type": "string"}},
    ["pasta"],
    risco=CONFIRMAR,
)
def organizar_pasta(pasta: str) -> str:
    base = resolver_caminho(pasta)
    plano = plano_organizacao(base)
    movidos, falhas = Counter(), []
    for cat, arquivos in plano.items():
        destino_pasta = base / cat
        destino_pasta.mkdir(exist_ok=True)
        for arquivo in arquivos:
            try:
                shutil.move(str(arquivo), str(_destino_livre(destino_pasta / arquivo.name)))
                movidos[cat] += 1
            except OSError:
                falhas.append(arquivo.name)  # em uso por outro programa, por exemplo
    if not movidos and not falhas:
        return f"Não havia arquivos soltos em {base}."
    resumo = ", ".join(f"{n} em {c}" for c, n in movidos.most_common())
    extra = f" Não consegui mover {len(falhas)} (em uso): {', '.join(falhas[:5])}." if falhas else ""
    return f"Pasta organizada: {resumo}.{extra}"


def _pasta_temporaria() -> Path:
    return Path(os.environ.get("TEMP") or tempfile.gettempdir())


def limpar_pasta_antiga(pasta: Path, dias: float = 2) -> tuple[int, int]:
    """Apaga arquivos mais velhos que `dias`. Devolve (quantidade, bytes liberados)."""
    limite = time.time() - dias * 86400
    qtd = liberado = 0
    for raiz, _dirs, arquivos in os.walk(pasta, topdown=False):
        for nome in arquivos:
            caminho = Path(raiz) / nome
            try:
                info = caminho.stat()
                if info.st_mtime < limite:
                    caminho.unlink()
                    qtd += 1
                    liberado += info.st_size
            except OSError:
                pass  # em uso: o Windows não deixa apagar, tudo bem
        if Path(raiz) != pasta:
            try:
                Path(raiz).rmdir()  # só remove se ficou vazia
            except OSError:
                pass
    return qtd, liberado


@ferramenta(
    "limpar_temporarios",
    "Apaga arquivos temporários antigos (mais de 2 dias) da pasta TEMP do Windows para liberar espaço.",
    risco=CONFIRMAR,
)
def limpar_temporarios() -> str:
    qtd, liberado = limpar_pasta_antiga(_pasta_temporaria())
    return f"Limpeza concluída: {qtd} arquivo(s) temporário(s) apagado(s), {_tamanho(liberado)} liberados."


@ferramenta("esvaziar_lixeira", "Esvazia a Lixeira do Windows (não dá para desfazer).", risco=CONFIRMAR)
def esvaziar_lixeira() -> str:
    if sys.platform != "win32":
        return "Disponível só no Windows."
    import ctypes

    # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
    resultado = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)  # type: ignore[attr-defined]
    return "Lixeira esvaziada." if resultado in (0, -2147418113) else f"Não consegui esvaziar a lixeira (código {resultado})."
