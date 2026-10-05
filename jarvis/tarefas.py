"""Lista de tarefas e lembretes que ficam salvos (dados/tarefas.json).

O Agendador roda em segundo plano e avisa na hora de cada lembrete — só
lembretes que o próprio usuário pediu; o JARVIS nunca puxa conversa sozinho.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from jarvis.config import config
from jarvis.tools import ferramenta

REPETICOES = ["nunca", "diario", "dias_uteis", "semanal"]
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _agora() -> datetime:
    return datetime.now().astimezone()


def _ler_data(texto: str) -> datetime:
    d = datetime.fromisoformat(texto.strip())
    return d if d.tzinfo else d.astimezone()


def _falar_data(d: datetime) -> str:
    hoje = _agora().date()
    if d.date() == hoje:
        dia = "hoje"
    elif d.date() == hoje + timedelta(days=1):
        dia = "amanhã"
    else:
        dia = f"{DIAS[d.weekday()]} {d:%d/%m}"
    return f"{dia} às {d:%H:%M}"


def proxima_ocorrencia(quando: datetime, repetir: str, depois_de: datetime) -> datetime | None:
    """Próxima data de um lembrete recorrente estritamente depois de `depois_de`."""
    if repetir == "nunca":
        return None
    passo = timedelta(weeks=1) if repetir == "semanal" else timedelta(days=1)
    d = quando
    while d <= depois_de or (repetir == "dias_uteis" and d.weekday() >= 5):
        d += passo
    return d


class Tarefas:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self.trava = threading.RLock()

    # -- armazenamento -----------------------------------------------------
    def _ler(self) -> dict[str, list[dict[str, Any]]]:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            dados = {}
        return {"tarefas": dados.get("tarefas", []), "lembretes": dados.get("lembretes", [])}

    def _gravar(self, dados: dict[str, Any]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.arquivo)

    @staticmethod
    def _achar(itens: list[dict[str, Any]], ref: str, campo: str) -> dict[str, Any] | None:
        ref = ref.strip().lower()
        for it in itens:
            if it["id"] == ref:
                return it
        for it in itens:
            if ref and ref in it[campo].lower():
                return it
        return None

    # -- tarefas -------------------------------------------------------------
    def adicionar_tarefa(self, titulo: str, prazo: str | None = None) -> dict[str, Any]:
        with self.trava:
            dados = self._ler()
            t = {
                "id": secrets.token_hex(3),
                "titulo": titulo.strip(),
                "prazo": _ler_data(prazo).isoformat() if prazo else None,
                "feita": False,
                "criada": _agora().isoformat(),
            }
            dados["tarefas"].append(t)
            self._gravar(dados)
            return t

    def tarefas(self, incluir_feitas: bool = False) -> list[dict[str, Any]]:
        lista = [t for t in self._ler()["tarefas"] if incluir_feitas or not t["feita"]]
        return sorted(lista, key=lambda t: (t["feita"], t["prazo"] or "9999", t["criada"]))

    def concluir_tarefa(self, ref: str, feita: bool = True) -> dict[str, Any] | None:
        with self.trava:
            dados = self._ler()
            t = self._achar(dados["tarefas"], ref, "titulo")
            if t:
                t["feita"] = feita
                self._gravar(dados)
            return t

    def apagar_tarefa(self, ref: str) -> dict[str, Any] | None:
        with self.trava:
            dados = self._ler()
            t = self._achar(dados["tarefas"], ref, "titulo")
            if t:
                dados["tarefas"].remove(t)
                self._gravar(dados)
            return t

    # -- lembretes -----------------------------------------------------------
    def criar_lembrete(self, mensagem: str, quando: str, repetir: str = "nunca") -> dict[str, Any]:
        if repetir not in REPETICOES:
            raise ValueError(f"repetir deve ser um de: {', '.join(REPETICOES)}")
        d = _ler_data(quando)
        if repetir == "nunca" and d < _agora() - timedelta(minutes=1):
            raise ValueError("Essa data já passou.")
        if repetir != "nunca" and d <= _agora():
            d = proxima_ocorrencia(d, repetir, _agora())
        with self.trava:
            dados = self._ler()
            lem = {"id": secrets.token_hex(3), "mensagem": mensagem.strip(), "quando": d.isoformat(), "repetir": repetir}
            dados["lembretes"].append(lem)
            self._gravar(dados)
            return lem

    def lembretes(self) -> list[dict[str, Any]]:
        return sorted(self._ler()["lembretes"], key=lambda lem: lem["quando"])

    def cancelar_lembrete(self, ref: str) -> dict[str, Any] | None:
        with self.trava:
            dados = self._ler()
            lem = self._achar(dados["lembretes"], ref, "mensagem")
            if lem:
                dados["lembretes"].remove(lem)
                self._gravar(dados)
            return lem

    def vencidos(self, agora: datetime | None = None) -> list[dict[str, Any]]:
        """Remove/reagenda os lembretes que já venceram e os devolve para avisar."""
        agora = agora or _agora()
        with self.trava:
            dados = self._ler()
            disparar = []
            for lem in list(dados["lembretes"]):
                quando = _ler_data(lem["quando"])
                if quando > agora:
                    continue
                disparar.append({**lem, "atrasado": agora - quando > timedelta(minutes=5)})
                proxima = proxima_ocorrencia(quando, lem["repetir"], agora)
                if proxima:
                    lem["quando"] = proxima.isoformat()
                else:
                    dados["lembretes"].remove(lem)
            if disparar:
                self._gravar(dados)
            return disparar


tarefas = Tarefas(config.pasta_dados / "tarefas.json")


class Agendador(threading.Thread):
    """Confere os lembretes a cada `intervalo` segundos e chama `avisar(texto)`."""

    def __init__(self, avisar: Callable[[str], None], intervalo: float = 15) -> None:
        super().__init__(daemon=True, name="jarvis-agendador")
        self.avisar = avisar
        self.intervalo = intervalo
        self.parar = threading.Event()

    def checar(self) -> None:
        for lem in tarefas.vencidos():
            prefixo = "Lembrete atrasado: " if lem["atrasado"] else "Lembrete: "
            try:
                self.avisar(prefixo + lem["mensagem"])
            except Exception:
                pass

    def run(self) -> None:
        while not self.parar.is_set():
            self.checar()
            self.parar.wait(self.intervalo)


# ---------------------------------------------------------------------------
# Ferramentas para o Claude
# ---------------------------------------------------------------------------


def _descrever_tarefa(t: dict[str, Any]) -> str:
    prazo = f" (prazo: {_falar_data(_ler_data(t['prazo']))})" if t.get("prazo") else ""
    return f"[{t['id']}] {'✓ ' if t['feita'] else ''}{t['titulo']}{prazo}"


def _descrever_lembrete(lem: dict[str, Any]) -> str:
    rep = "" if lem["repetir"] == "nunca" else f", repete: {lem['repetir'].replace('_', ' ')}"
    return f"[{lem['id']}] {lem['mensagem']} — {_falar_data(_ler_data(lem['quando']))}{rep}"


@ferramenta(
    "adicionar_tarefa",
    "Adiciona um item à lista de tarefas do usuário (fica salva).",
    {
        "titulo": {"type": "string"},
        "prazo": {"type": "string", "description": "Opcional. Data/hora ISO 8601 no horário local, ex.: 2026-10-06T18:00."},
    },
    ["titulo"],
)
def adicionar_tarefa(titulo: str, prazo: str | None = None) -> str:
    return "Tarefa adicionada: " + _descrever_tarefa(tarefas.adicionar_tarefa(titulo, prazo))


@ferramenta(
    "listar_tarefas",
    "Lista as tarefas pendentes (e as concluídas, se pedido).",
    {"incluir_feitas": {"type": "boolean"}},
)
def listar_tarefas(incluir_feitas: bool | None = None) -> str:
    lista = tarefas.tarefas(bool(incluir_feitas))
    return "\n".join(_descrever_tarefa(t) for t in lista) if lista else "Nenhuma tarefa pendente."


@ferramenta(
    "concluir_tarefa",
    "Marca uma tarefa como feita, pelo id ou por parte do título.",
    {"tarefa": {"type": "string"}},
    ["tarefa"],
)
def concluir_tarefa(tarefa: str) -> str:
    t = tarefas.concluir_tarefa(tarefa)
    return f"Concluída: {t['titulo']}" if t else "Não encontrei essa tarefa."


@ferramenta(
    "apagar_tarefa",
    "Remove uma tarefa da lista, pelo id ou por parte do título.",
    {"tarefa": {"type": "string"}},
    ["tarefa"],
)
def apagar_tarefa(tarefa: str) -> str:
    t = tarefas.apagar_tarefa(tarefa)
    return f"Removida: {t['titulo']}" if t else "Não encontrei essa tarefa."


@ferramenta(
    "criar_lembrete",
    "Agenda um lembrete que o JARVIS fala em voz alta na hora marcada (fica salvo mesmo se o PC reiniciar). "
    "Para 'daqui a X minutos', calcule a data a partir da hora atual.",
    {
        "mensagem": {"type": "string", "description": "O que dizer na hora, ex.: 'tirar o bolo do forno'."},
        "quando": {"type": "string", "description": "Data/hora ISO 8601 no horário local, ex.: 2026-10-06T07:30."},
        "repetir": {"type": "string", "enum": REPETICOES, "description": "Padrão: nunca."},
    },
    ["mensagem", "quando"],
)
def criar_lembrete(mensagem: str, quando: str, repetir: str | None = None) -> str:
    return "Lembrete criado: " + _descrever_lembrete(tarefas.criar_lembrete(mensagem, quando, repetir or "nunca"))


@ferramenta("listar_lembretes", "Lista os lembretes agendados.")
def listar_lembretes() -> str:
    lista = tarefas.lembretes()
    return "\n".join(_descrever_lembrete(lem) for lem in lista) if lista else "Nenhum lembrete agendado."


@ferramenta(
    "cancelar_lembrete",
    "Cancela um lembrete pelo id ou por parte da mensagem.",
    {"lembrete": {"type": "string"}},
    ["lembrete"],
)
def cancelar_lembrete(lembrete: str) -> str:
    lem = tarefas.cancelar_lembrete(lembrete)
    return f"Cancelado: {lem['mensagem']}" if lem else "Não encontrei esse lembrete."
