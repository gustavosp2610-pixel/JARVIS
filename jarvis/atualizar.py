"""Atualização automática: ao abrir, o JARVIS baixa a versão nova do GitHub (se houver).

Só troca os arquivos do programa. NUNCA mexe em:
  .env (chaves e senhas), dados/ (tarefas, gastos, memórias), .venv/ (bibliotecas),
  credentials.json / token.json (Google).
Se o requirements.txt mudou, instala as bibliotecas novas. Sem internet, não faz nada.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from jarvis.config import RAIZ, config

REPO = os.getenv("JARVIS_ATUALIZACAO_REPO", "gustavosp2610-pixel/JARVIS")
RAMO = os.getenv("JARVIS_ATUALIZACAO_RAMO", "claude/jarvis-iron-man-assistant-5dpk4u")
PROTEGIDOS = {".env", "dados", ".venv", "venv", "credentials.json", "token.json", ".git"}
# O .bat que está rodando só é trocado se já for do formato novo (que não quebra ao ser trocado).
MARCA_BAT_SEGURO = "JARVIS-BAT-SEGURO"
TEMPO_LIMITE = 8


def _baixar(url: str, tempo: float = TEMPO_LIMITE) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-atualizador", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=tempo) as resp:
        return resp.read()


def versao_remota() -> tuple[str, str]:
    """(sha, título do último commit) do ramo no GitHub."""
    dados = json.loads(_baixar(f"https://api.github.com/repos/{REPO}/commits/{RAMO}"))
    return dados["sha"], dados["commit"]["message"].splitlines()[0]


def baixar_zip() -> bytes:
    return _baixar(f"https://codeload.github.com/{REPO}/zip/refs/heads/{RAMO}", tempo=60)


def _arquivo_versao() -> Path:
    return config.pasta_dados / "versao.json"


def versao_local() -> str:
    try:
        return json.loads(_arquivo_versao().read_text(encoding="utf-8")).get("sha", "")
    except (OSError, json.JSONDecodeError):
        return ""


def _hash(caminho: Path) -> str:
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest()
    except OSError:
        return ""


def aplicar_zip(conteudo: bytes, destino: Path) -> list[str]:
    """Copia os arquivos do ZIP para `destino`, sem tocar nos protegidos. Devolve os arquivos alterados."""
    alterados = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nomes = [n for n in z.namelist() if not n.endswith("/")]
        prefixo = nomes[0].split("/", 1)[0] + "/" if nomes else ""
        for nome in nomes:
            relativo = nome[len(prefixo):]
            if not relativo or relativo.split("/", 1)[0] in PROTEGIDOS:
                continue
            alvo = destino / relativo
            dados = z.read(nome)
            if alvo.exists() and alvo.read_bytes() == dados:
                continue
            if alvo.suffix.lower() == ".bat" and alvo.exists() and MARCA_BAT_SEGURO not in alvo.read_text(errors="ignore"):
                continue  # .bat antigo pode estar rodando agora; trocar no meio quebraria o cmd
            alvo.parent.mkdir(parents=True, exist_ok=True)
            temporario = alvo.with_name(alvo.name + ".novo")
            temporario.write_bytes(dados)
            os.replace(temporario, alvo)
            alterados.append(relativo)
    return alterados


def instalar_bibliotecas(destino: Path) -> bool:
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--prefer-binary", "--disable-pip-version-check",
         "-r", str(destino / "requirements.txt")],
        check=False,
    )
    return r.returncode == 0


def atualizar_se_preciso(avisar: Callable[[str], None] = print, destino: Path = RAIZ) -> bool:
    """Atualiza se houver versão nova. Devolve True se arquivos do programa mudaram (precisa reiniciar)."""
    if os.getenv("JARVIS_ATUALIZAR_SOZINHO", "true").strip().lower() in {"0", "false", "nao", "não", "no"}:
        return False
    try:
        sha, titulo = versao_remota()
    except Exception:
        return False  # sem internet ou GitHub fora do ar: abre a versão que já tem
    if sha == versao_local():
        return False
    avisar(f"Baixando atualização: {titulo}")
    try:
        conteudo = baixar_zip()
    except Exception as e:
        avisar(f"Não consegui baixar a atualização ({type(e).__name__}). Abrindo a versão atual.")
        return False
    req_antes = _hash(destino / "requirements.txt")
    alterados = aplicar_zip(conteudo, destino)
    if _hash(destino / "requirements.txt") != req_antes:
        avisar("Instalando bibliotecas novas…")
        if not instalar_bibliotecas(destino):
            avisar("Algumas bibliotecas não instalaram; rode o instalar_jarvis.bat se algo não funcionar.")
    _arquivo_versao().write_text(json.dumps({"sha": sha, "titulo": titulo}, ensure_ascii=False), encoding="utf-8")
    avisar(f"Atualizado! ({len(alterados)} arquivo(s) novos)" if alterados else "Já estava com os arquivos mais novos.")
    return bool(alterados)
