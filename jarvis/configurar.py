"""Assistente de configuração: python -m jarvis --configurar

Pergunta o nome, ajuda a criar a chave GRÁTIS do Gemini, testa a chave e a voz,
e grava tudo no arquivo .env.
"""

from __future__ import annotations

import os
import re
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from jarvis.config import RAIZ

console = Console()
ARQUIVO_ENV = RAIZ / ".env"
LINK_CHAVE = "https://aistudio.google.com/apikey"
LINK_SENHA_APP = "https://myaccount.google.com/apppasswords"
TENTATIVAS_GMAIL = 3


def configurar_gmail() -> bool:
    """Conecta o Gmail com uma senha de app. Devolve True se ficou conectado."""
    from jarvis.tools.gmail_simples import limpar_endereco, testar_login

    atual = ler_env()
    console.print(
        "\n[bold cyan]Conectar o Gmail[/bold cyan] (para o JARVIS ler e enviar e-mails)\n"
        "Você vai criar uma [b]senha de app[/b]: uma senha especial só para o JARVIS. "
        "Sua conta Google precisa estar com a [b]verificação em duas etapas[/b] ligada.\n"
        f"1. Vou abrir [link={LINK_SENHA_APP}]{LINK_SENHA_APP}[/link].\n"
        "2. Em 'Nome do app' digite [b]JARVIS[/b] e clique em [b]Criar[/b].\n"
        "3. Copie a senha de 16 letras que aparecer e cole aqui.\n"
        "   (Se a página disser que a opção não está disponível, ligue antes a verificação em duas etapas em\n"
        "    myaccount.google.com → Segurança.)\n"
    )
    webbrowser.open(LINK_SENHA_APP)
    for tentativa in range(1, TENTATIVAS_GMAIL + 1):
        while True:
            endereco = Prompt.ask("Seu endereço do Gmail", default=atual.get("GMAIL_ENDERECO") or None)
            try:
                endereco = limpar_endereco(endereco or "")
                break
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
        senha = Prompt.ask("Cole a senha de app (16 letras)").replace(" ", "").strip()
        if not re.fullmatch(r"[A-Za-z]{16}", senha):
            console.print(
                f"[yellow]A senha de app tem exatamente 16 letras (você colou {len(senha)} caracteres). "
                "Não use a senha normal da sua conta nem a chave do Gemini.[/yellow]"
            )
            erro = "formato"
        else:
            console.print("Testando envio e leitura no Gmail…")
            erro = testar_login(endereco, senha)
        if not erro:
            gravar_env({"GMAIL_ENDERECO": endereco, "GMAIL_SENHA_APP": senha})
            os.environ.update({"GMAIL_ENDERECO": endereco, "GMAIL_SENHA_APP": senha})
            console.print("[green]Gmail conectado![/green] Reinicie o JARVIS para usar.")
            return True
        if erro != "formato":
            console.print(f"[red]Não funcionou: {erro}.[/red]")
            console.print(
                "Causas mais comuns:\n"
                "  • colou a senha normal da conta (precisa ser a senha de app de 16 letras);\n"
                "  • a verificação em duas etapas está desligada (myaccount.google.com → Segurança);\n"
                "  • o endereço do Gmail está com erro de digitação;\n"
                "  • a senha foi copiada pela metade. Na página do Google, crie uma nova e copie inteira."
            )
        if tentativa < TENTATIVAS_GMAIL and Confirm.ask("Tentar de novo?", default=True):
            continue
        break
    console.print("Nada foi salvo. Quando quiser, dê dois cliques em [b]conectar_gmail.bat[/b] para tentar de novo.")
    return False


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

    if atual.get("GMAIL_SENHA_APP"):
        from jarvis.tools.gmail_simples import testar_login

        console.print("Conferindo o Gmail salvo…")
        erro_gmail = testar_login(atual.get("GMAIL_ENDERECO", ""), atual["GMAIL_SENHA_APP"])
        if erro_gmail:
            console.print(f"[yellow]O Gmail salvo não funciona ({erro_gmail}). Vamos conectar de novo.[/yellow]")
            configurar_gmail()
        elif not Confirm.ask("O Gmail já está conectado e funcionando. Manter assim?", default=True):
            configurar_gmail()
    elif Confirm.ask("Quer conectar o Gmail agora (para ele ler e enviar e-mails)?", default=True):
        configurar_gmail()

    if Confirm.ask("Quer testar a voz agora?", default=True):
        from jarvis.voice.speaker import testar_voz

        erro_voz = testar_voz()
        if erro_voz:
            console.print(f"[yellow]A voz neural falhou:[/yellow] {erro_voz}")
            console.print("O JARVIS ainda funciona; a tela usará a voz do navegador.")
        else:
            console.print("[green]Voz funcionando![/green]")

    console.print("\n[bold cyan]Pronto![/bold cyan] Para ligar o JARVIS, use o atalho [b]JARVIS[/b] na Área de Trabalho.\n")
