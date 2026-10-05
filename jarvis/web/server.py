"""Servidor local da interface (HUD) do JARVIS.

Roda só em 127.0.0.1 — nada fica exposto na rede. Cada execução gera um token
secreto embutido na página; toda chamada da API precisa dele, então outros sites
abertos no seu navegador não conseguem mandar ordens para o JARVIS.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jarvis.config import config

PAGINA = Path(__file__).with_name("index.html")
TEMPO_CONFIRMACAO = 120  # segundos esperando o usuário autorizar uma ação


class Estado:
    """Fila de eventos (consumida pela página via long-polling) e confirmações pendentes."""

    def __init__(self) -> None:
        self.eventos: list[dict[str, Any]] = []
        self.cond = threading.Condition()
        self.confirmacoes: dict[str, dict[str, Any]] = {}
        self.ocupado = False
        self._cache_google: tuple[float, dict[str, Any]] | None = None

    def publicar(self, tipo: str, **dados: Any) -> None:
        with self.cond:
            self.eventos.append({"n": len(self.eventos), "tipo": tipo, **dados})
            self.cond.notify_all()

    def desde(self, n: int, espera: float) -> list[dict[str, Any]]:
        with self.cond:
            if len(self.eventos) <= n:
                self.cond.wait(timeout=espera)
            return self.eventos[n:]

    def confirmar(self, resumo: str) -> bool:
        """Chamado pelo cérebro (em outra thread): pergunta na tela e espera a resposta."""
        ident = secrets.token_hex(4)
        pendente = {"evento": threading.Event(), "aprovado": False}
        self.confirmacoes[ident] = pendente
        nome, _, args = resumo.partition("(")
        self.publicar(
            "confirmar",
            id=ident,
            acao=nome.replace("_", " "),
            detalhes=args.rstrip(")"),
        )
        pendente["evento"].wait(TEMPO_CONFIRMACAO)
        self.confirmacoes.pop(ident, None)
        self.publicar("confirmacao_encerrada", id=ident)
        return bool(pendente["aprovado"])

    def responder_confirmacao(self, ident: str, aprovado: bool) -> bool:
        pendente = self.confirmacoes.get(ident)
        if not pendente:
            return False
        pendente["aprovado"] = aprovado
        pendente["evento"].set()
        return True

    def dados_google(self) -> dict[str, Any]:
        agora = time.time()
        if self._cache_google and agora - self._cache_google[0] < 120:
            return self._cache_google[1]
        from jarvis.tools import google

        dados: dict[str, Any] = {"conectado": google.TOKEN.exists()}
        if dados["conectado"]:
            for chave, func, kwargs in (
                ("agenda", google.ver_agenda, {"dias": 1}),
                ("emails", google.ler_emails_recentes, {"filtro": "is:unread in:inbox", "quantidade": 6}),
            ):
                try:
                    dados[chave] = func(**kwargs)
                except Exception as e:  # sem internet, token expirado...
                    dados[chave] = f"Não consegui carregar: {e}"
        self._cache_google = (agora, dados)
        return dados


class _LogNaTela(logging.Handler):
    """Mostra avisos e erros do JARVIS no Registro de operações do HUD."""

    def __init__(self, estado: Estado) -> None:
        super().__init__(level=logging.WARNING)
        self.estado = estado

    def emit(self, registro: logging.LogRecord) -> None:
        try:
            self.estado.publicar("log", texto=registro.getMessage()[:300], nivel=registro.levelname)
        except Exception:
            pass


def _ligar_log_na_tela(estado: Estado) -> None:
    log = logging.getLogger("jarvis")
    for h in [h for h in log.handlers if isinstance(h, _LogNaTela)]:
        log.removeHandler(h)
    log.addHandler(_LogNaTela(estado))


def configurar_log() -> None:
    """Avisos e erros aparecem na janela preta, com horário."""
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def criar_servidor(porta: int = 8765, agendar: bool = True) -> tuple[ThreadingHTTPServer, str]:
    from jarvis import preferencias
    from jarvis.brain import criar_cerebro
    from jarvis.memory import memoria
    from jarvis.rotinas import rotinas
    from jarvis.tarefas import Agendador, tarefas
    from jarvis.tools.financas import financas
    from jarvis.tools import computer
    from jarvis.voice import speaker

    token = secrets.token_urlsafe(24)
    estado = Estado()
    cerebro = criar_cerebro(
        confirmar=estado.confirmar,
        ao_usar_ferramenta=lambda nome: estado.publicar("ferramenta", nome=nome),
        ao_progresso=lambda texto: estado.publicar("progresso", texto=texto),
        ao_acao_pc=lambda texto: estado.publicar("acao_pc", texto=texto),
    )
    computer.avisar = lambda texto: estado.publicar("aviso", texto=texto)
    _ligar_log_na_tela(estado)
    if agendar:
        Agendador(computer.avisar).start()
    cache_vozes: list[dict[str, Any]] = []
    hosts_validos: set[str] = set()  # preenchido depois que a porta real é conhecida

    def processar(texto: str) -> None:
        try:
            resposta = cerebro.responder(texto)
            estado.publicar("resposta", texto=resposta)
        except Exception as e:
            estado.publicar("resposta", texto=f"Algo deu errado aqui dentro, senhor: {e}")
        finally:
            estado.ocupado = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # silencia o log padrão
            pass

        # -- utilitários ---------------------------------------------------
        def _json(self, dados: Any, status: int = 200) -> None:
            corpo = json.dumps(dados, ensure_ascii=False, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _autorizado(self, query: dict[str, list[str]]) -> bool:
            if self.headers.get("Host") not in hosts_validos:
                return False
            enviado = self.headers.get("X-Jarvis-Token") or query.get("t", [""])[0]
            return secrets.compare_digest(enviado, token)

        def _corpo(self) -> dict[str, Any]:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if not tamanho:
                return {}
            return json.loads(self.rfile.read(min(tamanho, 100_000)) or b"{}")

        # -- rotas ---------------------------------------------------------
        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                if self.headers.get("Host") not in hosts_validos:
                    return self.send_error(HTTPStatus.FORBIDDEN)
                html = PAGINA.read_text(encoding="utf-8").replace("__JARVIS_TOKEN__", token)
                pagina = (
                    '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                    f"</head><body>{html}</body></html>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(pagina)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(pagina)
                return
            if not url.path.startswith("/api/"):
                return self.send_error(HTTPStatus.NOT_FOUND)
            if not self._autorizado(query):
                return self.send_error(HTTPStatus.FORBIDDEN)

            if url.path == "/api/eventos":
                n = int(query.get("desde", ["0"])[0])
                espera = min(float(query.get("espera", ["20"])[0]), 25)
                return self._json({"eventos": estado.desde(n, espera), "ocupado": estado.ocupado})
            if url.path == "/api/painel":
                from jarvis.tools.computer import info_sistema

                return self._json(
                    {
                        "nome": config.nome_usuario,
                        "modelo": config.modelo_ativo,
                        "sistema": info_sistema(),
                        "memorias": memoria.fatos(),
                        "tarefas": tarefas.tarefas(incluir_feitas=False)[:12],
                        "rotinas": rotinas.nomes(),
                        "financas": financas.resumo(),
                        "lembretes": tarefas.lembretes()[:6],
                        "voz": preferencias.carregar(),
                        "google": estado.dados_google(),
                    }
                )
            if url.path == "/api/vozes":
                if not cache_vozes:
                    try:
                        cache_vozes.extend(speaker.listar_vozes())
                    except Exception as e:
                        return self._json({"erro": f"Não consegui listar as vozes: {e}"}, 503)
                return self._json({"vozes": cache_vozes, "atual": preferencias.carregar()})
            if url.path == "/api/voz":
                texto = speaker.preparar_para_fala(query.get("texto", [""])[0][:3000], limite=3000)
                try:
                    audio = speaker.sintetizar(texto)
                except Exception as e:
                    return self._json({"erro": f"{type(e).__name__}: {e}"}, 503)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if not self._autorizado(parse_qs(url.query)):
                return self.send_error(HTTPStatus.FORBIDDEN)
            dados = self._corpo()

            if url.path == "/api/mensagem":
                texto = str(dados.get("texto", "")).strip()
                if not texto:
                    return self._json({"erro": "Mensagem vazia."}, 400)
                if estado.ocupado:
                    return self._json({"erro": "Ainda estou cuidando do pedido anterior."}, 409)
                estado.ocupado = True
                threading.Thread(target=processar, args=(texto,), daemon=True).start()
                return self._json({"ok": True})
            if url.path == "/api/confirmar":
                ok = estado.responder_confirmacao(str(dados.get("id")), bool(dados.get("aprovado")))
                return self._json({"ok": ok})
            if url.path == "/api/parar":
                cerebro.parar()
                return self._json({"ok": True})
            if url.path == "/api/preferencias":
                try:
                    return self._json(preferencias.salvar(dados))
                except (ValueError, TypeError) as e:
                    return self._json({"erro": str(e)}, 400)
            if url.path == "/api/tarefas/concluir":
                t = tarefas.concluir_tarefa(str(dados.get("id", "")), bool(dados.get("feita", True)))
                return self._json({"ok": bool(t)})
            if url.path == "/api/nova-conversa":
                if estado.ocupado:
                    return self._json({"erro": "Espere eu terminar o pedido atual."}, 409)
                cerebro.nova_conversa()
                return self._json({"ok": True})
            self.send_error(HTTPStatus.NOT_FOUND)

    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    servidor.daemon_threads = True
    porta_real = servidor.server_address[1]
    hosts_validos.update({f"127.0.0.1:{porta_real}", f"localhost:{porta_real}"})
    return servidor, token


def iniciar(porta: int = 8765, abrir_navegador: bool = True) -> None:
    from rich.console import Console

    console = Console()
    configurar_log()
    servidor, _ = criar_servidor(porta)
    url = f"http://localhost:{porta}/"
    console.print(f"[bold cyan]J.A.R.V.I.S. online[/bold cyan] em [link={url}]{url}[/link]")
    console.print("[dim]Deixe esta janela aberta. Ctrl+C para desligar.[/dim]")
    if abrir_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
        console.print("[cyan]Até logo, senhor.[/cyan]")
