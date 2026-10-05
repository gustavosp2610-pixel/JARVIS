"""Estudos e produtividade: ler PDFs/Word/páginas, anotações e pomodoro."""

from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from jarvis.tools import ferramenta
from jarvis.tools.computer import HOME, resolver_caminho

LIMITE_TEXTO = 40_000
PASTA_ANOTACOES = HOME / "Documents" / "JARVIS" / "Anotações"


def _cortar(texto: str) -> str:
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if len(texto) > LIMITE_TEXTO:
        return texto[:LIMITE_TEXTO] + f"\n[... cortado: o documento tem {len(texto)} caracteres; peça as partes seguintes se precisar]"
    return texto


def texto_de_docx(caminho: Path) -> str:
    """Lê o texto de um .docx direto do XML (sem bibliotecas que precisem ser compiladas)."""
    import zipfile
    from xml.etree import ElementTree as ET

    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(caminho) as z:
        raiz = ET.fromstring(z.read("word/document.xml"))
    paragrafos = []
    for par in raiz.iter(f"{w}p"):
        partes = []
        for no in par.iter():
            if no.tag == f"{w}t" and no.text:
                partes.append(no.text)
            elif no.tag == f"{w}tab":
                partes.append("\t")
            elif no.tag in (f"{w}br", f"{w}cr"):
                partes.append("\n")
        paragrafos.append("".join(partes))
    return "\n".join(paragrafos)


def extrair_texto(caminho: Path) -> str:
    sufixo = caminho.suffix.lower()
    if sufixo == ".pdf":
        from pypdf import PdfReader

        leitor = PdfReader(str(caminho))
        paginas, tem_texto = [], False
        for i, pagina in enumerate(leitor.pages, 1):
            texto = (pagina.extract_text() or "").strip()
            tem_texto = tem_texto or bool(texto)
            paginas.append(f"--- página {i} ---\n{texto}")
            if sum(len(p) for p in paginas) > LIMITE_TEXTO:
                break
        return "\n".join(paginas) if tem_texto else ""
    if sufixo == ".docx":
        return texto_de_docx(caminho)
    if sufixo in {".txt", ".md", ".csv", ".json", ".py", ".html", ".log"}:
        return caminho.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Não sei ler arquivos {sufixo or 'sem extensão'}. Uso PDF, Word (.docx) e textos.")


@ferramenta(
    "ler_documento",
    "Lê o texto de um PDF, documento Word (.docx) ou arquivo de texto, para resumir, explicar, tirar dúvidas "
    "ou criar flashcards. Aceita apelidos de pasta (downloads/arquivo.pdf).",
    {"caminho": {"type": "string"}},
    ["caminho"],
)
def ler_documento(caminho: str) -> str:
    p = resolver_caminho(caminho)
    if not p.is_file():
        return f"{p} não é um arquivo. Use procurar_arquivos para achar o caminho certo."
    texto = extrair_texto(p)
    return _cortar(texto) if texto.strip() else "O documento não tem texto legível (pode ser uma imagem escaneada)."


class _ExtratorTexto(HTMLParser):
    IGNORAR = {"script", "style", "noscript", "nav", "footer", "header", "svg", "form"}
    BLOCOS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        self.titulo = ""
        self._ignorando = 0
        self._no_titulo = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.IGNORAR:
            self._ignorando += 1
        elif tag == "title":
            self._no_titulo = True
        elif tag in self.BLOCOS:
            self.partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.IGNORAR and self._ignorando:
            self._ignorando -= 1
        elif tag == "title":
            self._no_titulo = False

    def handle_data(self, dados: str) -> None:
        if self._no_titulo:
            self.titulo += dados
        elif not self._ignorando and dados.strip():
            self.partes.append(dados.strip() + " ")


def texto_de_html(html: str) -> tuple[str, str]:
    ext = _ExtratorTexto()
    ext.feed(html)
    texto = "".join(ext.partes)
    texto = "\n".join(linha.strip() for linha in texto.splitlines() if linha.strip())
    return ext.titulo.strip(), texto


@ferramenta(
    "ler_pagina_web",
    "Baixa uma página da internet e devolve o texto principal, para resumir artigos, notícias ou tutoriais.",
    {"url": {"type": "string"}},
    ["url"],
)
def ler_pagina_web(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        bruto = resp.read(3_000_000)
        charset = resp.headers.get_content_charset() or "utf-8"
    titulo, texto = texto_de_html(bruto.decode(charset, errors="replace"))
    return _cortar(f"Título: {titulo}\n\n{texto}" if titulo else texto) or "A página não tem texto legível."


# ---------------------------------------------------------------------------
# Anotações (arquivos .md em Documentos\JARVIS\Anotações)
# ---------------------------------------------------------------------------


def _nome_arquivo(titulo: str) -> str:
    limpo = re.sub(r'[<>:"/\\|?*\n\r\t]', "", titulo).strip()[:80] or "anotação"
    return f"{limpo}.md"


@ferramenta(
    "salvar_anotacao",
    "Salva uma anotação (ditado, resumo, flashcards, lista) como arquivo em Documentos\\JARVIS\\Anotações. "
    "Se já existir uma com o mesmo título, acrescenta o texto no final.",
    {"titulo": {"type": "string"}, "texto": {"type": "string"}},
    ["titulo", "texto"],
)
def salvar_anotacao(titulo: str, texto: str) -> str:
    PASTA_ANOTACOES.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_ANOTACOES / _nome_arquivo(titulo)
    carimbo = f"_{datetime.now():%d/%m/%Y %H:%M}_"
    if arquivo.exists():
        with arquivo.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{carimbo}\n\n{texto.strip()}\n")
        return f"Texto acrescentado à anotação '{titulo}'."
    arquivo.write_text(f"# {titulo}\n\n{carimbo}\n\n{texto.strip()}\n", encoding="utf-8")
    return f"Anotação salva em {arquivo}."


@ferramenta("listar_anotacoes", "Lista as anotações salvas (mais recentes primeiro).")
def listar_anotacoes() -> str:
    if not PASTA_ANOTACOES.is_dir():
        return "Nenhuma anotação salva ainda."
    arquivos = sorted(PASTA_ANOTACOES.glob("*.md"), key=lambda a: a.stat().st_mtime, reverse=True)
    return "\n".join(f"- {a.stem} ({datetime.fromtimestamp(a.stat().st_mtime):%d/%m %H:%M})" for a in arquivos[:50]) or "Nenhuma anotação salva ainda."


@ferramenta(
    "ler_anotacao",
    "Lê uma anotação salva pelo título (ou parte dele).",
    {"titulo": {"type": "string"}},
    ["titulo"],
)
def ler_anotacao(titulo: str) -> str:
    if not PASTA_ANOTACOES.is_dir():
        return "Nenhuma anotação salva ainda."
    alvo = titulo.lower().strip()
    for a in sorted(PASTA_ANOTACOES.glob("*.md"), key=lambda a: a.stat().st_mtime, reverse=True):
        if alvo in a.stem.lower():
            return _cortar(a.read_text(encoding="utf-8"))
    return "Não encontrei essa anotação."


# ---------------------------------------------------------------------------
# Pomodoro
# ---------------------------------------------------------------------------


@ferramenta(
    "pomodoro",
    "Inicia ciclos de pomodoro: o JARVIS avisa em voz alta quando for hora da pausa e de voltar ao foco.",
    {
        "minutos_foco": {"type": "integer", "description": "Padrão 25."},
        "minutos_pausa": {"type": "integer", "description": "Padrão 5."},
        "ciclos": {"type": "integer", "description": "Quantos ciclos de foco. Padrão 1, máximo 8."},
    },
)
def pomodoro(minutos_foco: int | None = None, minutos_pausa: int | None = None, ciclos: int | None = None) -> str:
    from jarvis.tarefas import tarefas

    foco = max(1, int(minutos_foco or 25))
    pausa = max(1, int(minutos_pausa or 5))
    n = max(1, min(8, int(ciclos or 1)))
    momento = datetime.now().astimezone()
    for i in range(1, n + 1):
        momento += timedelta(minutes=foco)
        ultimo = i == n
        msg = "Pomodoro concluído! Bom trabalho." if ultimo else f"Fim do foco {i} de {n}. Pausa de {pausa} minutos."
        tarefas.criar_lembrete(msg, momento.isoformat())
        if not ultimo:
            momento += timedelta(minutes=pausa)
            tarefas.criar_lembrete(f"Fim da pausa. Hora do foco {i + 1} de {n}.", momento.isoformat())
    return f"Pomodoro iniciado: {n} ciclo(s) de {foco} min de foco e {pausa} de pausa. Termina às {momento:%H:%M}."
