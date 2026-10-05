"""Ponto de entrada: python -m jarvis [--voz | --texto | --google]"""

from __future__ import annotations

import argparse
import os
import sys

from rich.console import Console

from jarvis.config import config

console = Console()

SAIR = {"sair", "tchau", "desligar jarvis", "encerrar", "até mais", "ate mais"}
NOVA = {"nova conversa", "esquece a conversa", "limpar conversa"}
SIM = {"sim", "pode", "pode sim", "claro", "confirmo", "confirmado", "vai", "manda", "positivo", "ok", "isso", "autorizo"}


def _descrever(resumo: str) -> str:
    nome, _, args = resumo.partition("(")
    return f"{nome.replace('_', ' ')}: {args.rstrip(')')}"[:200]


def _eh_sim(resposta: str | None) -> bool:
    if not resposta:
        return False
    r = resposta.lower().strip(" .!,")
    return r in SIM or r.split()[0].strip(" .!,") in SIM


def _checar_chave() -> None:
    chaves = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    if not any(os.getenv(c) for c in chaves):
        console.print(
            "[red]Nenhuma chave de IA configurada.[/red] Rode [b]python -m jarvis --configurar[/b] "
            "para colocar sua chave grátis do Gemini (https://aistudio.google.com/apikey)."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Modo texto
# ---------------------------------------------------------------------------


def _mostradores() -> dict:
    """Mostra no terminal o que o JARVIS está fazendo."""
    return {
        "ao_usar_ferramenta": lambda n: console.print(f"[dim]  ↳ {n}[/dim]"),
        "ao_progresso": lambda t: console.print(f"[dim cyan]  … {t}[/dim cyan]"),
        "ao_acao_pc": lambda t: console.print(f"[dim]  🖱 {t}[/dim]"),
    }


def modo_texto(com_voz: bool) -> None:
    from jarvis.brain import criar_cerebro
    from jarvis.tarefas import Agendador
    from jarvis.tools import computer

    falar = None
    if com_voz:
        from jarvis.voice.speaker import falar

    def confirmar(resumo: str) -> bool:
        console.print(f"[yellow]⚠ Ação sensível:[/yellow] {resumo}")
        return _eh_sim(console.input("[yellow]Posso prosseguir? (sim/não) [/yellow]"))

    def aviso(texto: str) -> None:
        console.print(f"\n[bold cyan]⏰ JARVIS:[/bold cyan] {texto}")
        if falar:
            falar(texto)

    computer.avisar = aviso
    Agendador(aviso).start()
    cerebro = criar_cerebro(confirmar=confirmar, **_mostradores())
    console.print("[bold cyan]J.A.R.V.I.S. online.[/bold cyan] Digite 'sair' para encerrar.\n")
    while True:
        try:
            pedido = console.input("[bold]Você:[/bold] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pedido:
            continue
        if pedido.lower() in SAIR:
            break
        if pedido.lower() in NOVA:
            cerebro.nova_conversa()
            console.print("[dim]Conversa reiniciada.[/dim]")
            continue
        with console.status("[cyan]Processando...[/cyan]"):
            resposta = cerebro.responder(pedido)
        console.print(f"[bold cyan]JARVIS:[/bold cyan] {resposta}\n")
        if falar:
            falar(resposta)
    console.print("[cyan]Até logo, senhor.[/cyan]")


# ---------------------------------------------------------------------------
# Modo voz
# ---------------------------------------------------------------------------


def modo_voz() -> None:
    from jarvis.brain import criar_cerebro
    from jarvis.tarefas import Agendador
    from jarvis.tools import computer
    from jarvis.voice.listener import Ouvinte, extrair_comando
    from jarvis.voice.speaker import falar

    try:
        ouvinte = Ouvinte()
    except Exception as e:
        console.print(f"[red]Não consegui acessar o microfone ({e}).[/red] Usando modo texto.")
        return modo_texto(com_voz=True)

    def dizer(texto: str) -> None:
        console.print(f"[bold cyan]JARVIS:[/bold cyan] {texto}")
        falar(texto)

    def confirmar(resumo: str) -> bool:
        console.print(f"[yellow]⚠ Ação sensível:[/yellow] {resumo}")
        dizer(f"Antes, preciso da sua autorização para {_descrever(resumo)}. Posso prosseguir?")
        resposta = ouvinte.ouvir(espera=8, tempo_max=5)
        console.print(f"[dim]Você: {resposta or '(silêncio)'}[/dim]")
        return _eh_sim(resposta)

    computer.avisar = dizer
    Agendador(dizer).start()
    cerebro = criar_cerebro(confirmar=confirmar, **_mostradores())
    dizer(f"Sistemas online. Às suas ordens, {config.nome_usuario}.")
    console.print(f"[dim]Diga \"{config.palavra_ativacao.title()}\" seguido do pedido. Ctrl+C para sair.[/dim]")

    em_conversa = False  # logo após uma resposta, não precisa repetir "Jarvis"
    while True:
        try:
            frase = ouvinte.ouvir(espera=7 if em_conversa else None)
        except KeyboardInterrupt:
            break
        if not frase:
            em_conversa = False
            continue

        comando = frase if em_conversa else extrair_comando(frase)
        if comando is None:
            continue
        console.print(f"[bold]Você:[/bold] {frase}")
        if comando == "":
            dizer("Pois não?")
            comando = ouvinte.ouvir(espera=8) or ""
            if not comando:
                continue
            console.print(f"[bold]Você:[/bold] {comando}")

        normal = comando.lower().strip(" .!")
        if normal in SAIR:
            dizer("Desligando. Até logo, senhor.")
            break
        if normal in NOVA:
            cerebro.nova_conversa()
            dizer("Conversa reiniciada.")
            continue

        with console.status("[cyan]Processando...[/cyan]"):
            resposta = cerebro.responder(comando)
        dizer(resposta)
        em_conversa = True


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis", description="J.A.R.V.I.S. — seu assistente pessoal")
    parser.add_argument("--voz", action="store_true", help="modo voz no terminal, sem a tela")
    parser.add_argument("--texto", action="store_true", help="conversar digitando no terminal")
    parser.add_argument("--falar", action="store_true", help="no modo texto, também responder em voz alta")
    parser.add_argument("--google", action="store_true", help="conectar sua conta Google (Gmail/Agenda)")
    parser.add_argument("--gmail", action="store_true", help="conectar o Gmail com uma senha de app")
    parser.add_argument("--configurar", action="store_true", help="assistente de configuração (chave grátis, nome, voz)")
    parser.add_argument("--testar-voz", action="store_true", help="testa a voz neural e mostra o erro, se houver")
    parser.add_argument("--porta", type=int, default=8765, help="porta da tela (padrão 8765)")
    parser.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador automaticamente")
    args = parser.parse_args()

    if args.google:
        from jarvis.tools.google import autorizar

        autorizar(interativo=True)
        console.print("[green]Conta Google conectada![/green]")
        return

    if args.gmail:
        from jarvis.configurar import configurar_gmail

        configurar_gmail()
        return

    if args.configurar:
        from jarvis.configurar import configurar

        configurar()
        return

    if args.testar_voz:
        from jarvis import preferencias
        from jarvis.voice.speaker import testar_voz

        voz, rate, pitch = preferencias.prosodia()
        console.print(f"Testando a voz [b]{voz}[/b] (velocidade {rate}, tom {pitch})...")
        erro = testar_voz()
        if erro:
            console.print(f"[red]A voz neural falhou:[/red] {erro}")
            console.print("Dicas: confira a internet e rode [b]pip install -U edge-tts[/b].")
        else:
            console.print("[green]Voz neural funcionando![/green]")
        return

    _checar_chave()
    from jarvis.web.server import configurar_log

    configurar_log()
    if args.texto:
        modo_texto(com_voz=args.falar)
    elif args.voz:
        modo_voz()
    else:
        from jarvis.web.server import iniciar

        iniciar(porta=args.porta, abrir_navegador=not args.sem_navegador)


if __name__ == "__main__":
    main()
