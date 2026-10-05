"""Assistente de configuração: python -m jarvis --configurar

Pergunta o nome, ajuda a criar a chave GRÁTIS do Gemini, testa a chave e a voz,
e grava tudo no arquivo .env.
"""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from jarvis.config import RAIZ

console = Console()
ARQUIVO_ENV = RAIZ / ".env"
LINK_CHAVE = "https://aistudio.google.com/apikey"


def ler_env(arquivo: Path = ARQUIVO_ENV) -> dict[str, str]:
    valores: dict[str, str] = {}
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip()
    return valores


def gravar_env(novos: dict[str, str], arquivo: Path = ARQUIVO_ENV) -> None:
    """Atualiza/adiciona chaves no .env mantendo comentários e o resto do arquivo."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []
    pendentes = dict(novos)
    for i, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if "=" in linha and not linha.lstrip().startswith("#") and chave in pendentes:
            linhas[i] = f"{chave}={pendentes.pop(chave)}"
    linhas += [f"{k}={v}" for k, v in pendentes.items()]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def testar_chave_gemini(chave: str, modelo: str) -> str | None:
    """Faz uma pergunta curtinha. Devolve None se funcionou, ou a explicação do erro."""
    from google import genai
    from google.genai import errors

    from jarvis.cerebro_gemini import _mensagem_erro

    try:
        resp = genai.Client(api_key=chave).models.generate_content(model=modelo, contents="Responda apenas: ok")
        return None if resp.text else "A chave respondeu vazio."
    except errors.APIError as e:
        return _mensagem_erro(e)
    except Exception as e:
        return f"Não consegui falar com o Google ({type(e).__name__}). Verifique a internet."


def configurar() -> None:
    atual = ler_env()
    console.print("\n[bold cyan]J.A.R.V.I.S. · Configuração[/bold cyan]\n")

    nome = Prompt.ask("Como o JARVIS deve te chamar?", default=atual.get("JARVIS_NOME_USUARIO", "senhor"))
    cidade = Prompt.ask("Sua cidade (para clima e notícias locais)", default=atual.get("JARVIS_CIDADE", ""))

    modelo = atual.get("JARVIS_MODELO_GEMINI", "gemini-flash-latest")
    chave = atual.get("GEMINI_API_KEY", "")
    if chave and Confirm.ask("Já existe uma chave do Gemini salva. Manter essa?", default=True):
        pass
    else:
        console.print(
            "\nO cérebro do JARVIS é o [b]Google Gemini[/b], [green]grátis[/green]. Você só precisa de uma conta Google.\n"
            f"1. Vou abrir [link={LINK_CHAVE}]{LINK_CHAVE}[/link] no navegador.\n"
            "2. Clique em [b]Criar chave de API[/b] (Create API key) e copie a chave.\n"
            "3. Volte aqui e cole com o botão direito do mouse (ou Ctrl+V).\n"
        )
        webbrowser.open(LINK_CHAVE)
        chave = ""
        while not chave:
            chave = Prompt.ask("Cole a chave aqui").strip().strip('"')

    console.print("Testando a chave…")
    erro = testar_chave_gemini(chave, modelo)
    if erro:
        console.print(f"[red]A chave não funcionou:[/red] {erro}")
        if not Confirm.ask("Salvar mesmo assim?", default=False):
            console.print("Nada foi salvo. Rode [b]python -m jarvis --configurar[/b] de novo quando quiser.")
            return
    else:
        console.print("[green]Chave funcionando![/green]")

    gravar_env(
        {
            "GEMINI_API_KEY": chave,
            "JARVIS_IA": "gemini",
            "JARVIS_NOME_USUARIO": nome,
            "JARVIS_CIDADE": cidade,
        }
    )
    os.environ.update({"GEMINI_API_KEY": chave, "JARVIS_IA": "gemini"})
    console.print(f"[green]Configuração salva em[/green] {ARQUIVO_ENV}")

    if Confirm.ask("Quer testar a voz agora?", default=True):
        from jarvis.voice.speaker import testar_voz

        erro_voz = testar_voz()
        if erro_voz:
            console.print(f"[yellow]A voz neural falhou:[/yellow] {erro_voz}")
            console.print("O JARVIS ainda funciona; a tela usará a voz do navegador.")
        else:
            console.print("[green]Voz funcionando![/green]")

    console.print("\n[bold cyan]Pronto![/bold cyan] Para ligar o JARVIS, use o atalho [b]JARVIS[/b] na Área de Trabalho.\n")
