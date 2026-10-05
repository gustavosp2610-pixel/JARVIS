"""Controle de gastos e receitas por voz ("gastei 30 no mercado")."""

from __future__ import annotations

import json
import secrets
import threading
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jarvis.config import config
from jarvis.tools import ferramenta


def _mes(texto: str | None) -> str:
    """'2026-10', '10/2026', '10' ou vazio (mês atual) -> 'AAAA-MM'."""
    hoje = date.today()
    if not texto:
        return f"{hoje:%Y-%m}"
    t = texto.strip()
    if len(t) == 7 and t[4] == "-":
        return t
    if "/" in t:
        m, a = t.split("/", 1)
        return f"{int(a):04d}-{int(m):02d}"
    return f"{hoje.year:04d}-{int(t):02d}"


def _reais(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Financas:
    def __init__(self, arquivo: Path) -> None:
        self.arquivo = arquivo
        self.trava = threading.RLock()

    def _ler(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8")).get("lancamentos", [])
        except (OSError, json.JSONDecodeError):
            return []

    def _gravar(self, lancamentos: list[dict[str, Any]]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps({"lancamentos": lancamentos}, ensure_ascii=False, indent=2), encoding="utf-8")

    def lancar(self, tipo: str, valor: float, descricao: str, categoria: str | None = None, data: str | None = None) -> dict[str, Any]:
        valor = round(abs(float(valor)), 2)
        if valor == 0:
            raise ValueError("O valor precisa ser maior que zero.")
        dia = date.fromisoformat(data[:10]) if data else date.today()
        item = {
            "id": secrets.token_hex(3),
            "tipo": tipo,
            "valor": valor,
            "descricao": descricao.strip(),
            "categoria": (categoria or "outros").strip().lower(),
            "data": dia.isoformat(),
            "criado": datetime.now().isoformat(timespec="seconds"),
        }
        with self.trava:
            todos = self._ler()
            todos.append(item)
            self._gravar(todos)
        return item

    def do_mes(self, mes: str | None = None) -> list[dict[str, Any]]:
        alvo = _mes(mes)
        return sorted((x for x in self._ler() if x["data"].startswith(alvo)), key=lambda x: x["data"], reverse=True)

    def resumo(self, mes: str | None = None) -> dict[str, Any]:
        itens = self.do_mes(mes)
        gastos = [x for x in itens if x["tipo"] == "gasto"]
        receitas = [x for x in itens if x["tipo"] == "receita"]
        por_categoria: dict[str, float] = defaultdict(float)
        for g in gastos:
            por_categoria[g["categoria"]] += g["valor"]
        total_gastos = round(sum(g["valor"] for g in gastos), 2)
        total_receitas = round(sum(r["valor"] for r in receitas), 2)
        return {
            "mes": _mes(mes),
            "gastos": total_gastos,
            "receitas": total_receitas,
            "saldo": round(total_receitas - total_gastos, 2),
            "categorias": sorted(((c, round(v, 2)) for c, v in por_categoria.items()), key=lambda cv: -cv[1]),
            "quantidade": len(itens),
        }

    def apagar(self, ident: str) -> dict[str, Any] | None:
        with self.trava:
            todos = self._ler()
            for x in todos:
                if x["id"] == ident.strip():
                    todos.remove(x)
                    self._gravar(todos)
                    return x
        return None


financas = Financas(config.pasta_dados / "financas.json")

_PROPS = {
    "valor": {"type": "number", "description": "Em reais, ex.: 30.5"},
    "descricao": {"type": "string", "description": "Ex.: 'mercado', 'Uber para o trabalho'."},
    "categoria": {
        "type": "string",
        "description": "Uma palavra: mercado, alimentação, transporte, lazer, contas, saúde, educação, compras, salário, outros.",
    },
    "data": {"type": "string", "description": "Opcional, AAAA-MM-DD. Padrão: hoje."},
}


@ferramenta("registrar_gasto", "Anota um gasto do usuário (ex.: 'gastei 30 no mercado').", _PROPS, ["valor", "descricao"])
def registrar_gasto(valor: float, descricao: str, categoria: str | None = None, data: str | None = None) -> str:
    g = financas.lancar("gasto", valor, descricao, categoria, data)
    r = financas.resumo()
    return f"Gasto anotado: {_reais(g['valor'])} em {g['categoria']} ({g['descricao']}). Total gasto no mês: {_reais(r['gastos'])}."


@ferramenta("registrar_receita", "Anota um dinheiro recebido (salário, pix recebido, venda...).", _PROPS, ["valor", "descricao"])
def registrar_receita(valor: float, descricao: str, categoria: str | None = None, data: str | None = None) -> str:
    g = financas.lancar("receita", valor, descricao, categoria or "receita", data)
    return f"Receita anotada: {_reais(g['valor'])} ({g['descricao']})."


@ferramenta(
    "resumo_financeiro",
    "Resumo do mês: total gasto, recebido, saldo e gastos por categoria.",
    {"mes": {"type": "string", "description": "Opcional: AAAA-MM ou MM/AAAA. Padrão: mês atual."}},
)
def resumo_financeiro(mes: str | None = None) -> str:
    r = financas.resumo(mes)
    if not r["quantidade"]:
        return f"Nenhum lançamento em {r['mes']}."
    cats = "; ".join(f"{c}: {_reais(v)}" for c, v in r["categorias"]) or "nenhum gasto"
    return (
        f"Mês {r['mes']}: gastos {_reais(r['gastos'])}, receitas {_reais(r['receitas'])}, saldo {_reais(r['saldo'])}. "
        f"Por categoria: {cats}."
    )


@ferramenta(
    "listar_lancamentos",
    "Lista os gastos e receitas do mês (com id, para apagar algum errado).",
    {"mes": {"type": "string", "description": "Opcional: AAAA-MM ou MM/AAAA."}},
)
def listar_lancamentos(mes: str | None = None) -> str:
    itens = financas.do_mes(mes)
    if not itens:
        return "Nenhum lançamento nesse mês."
    return "\n".join(
        f"[{x['id']}] {x['data'][8:10]}/{x['data'][5:7]} {'-' if x['tipo'] == 'gasto' else '+'}{_reais(x['valor'])} "
        f"{x['descricao']} ({x['categoria']})"
        for x in itens[:60]
    )


@ferramenta("apagar_lancamento", "Apaga um gasto ou receita pelo id (veja listar_lancamentos).", {"id": {"type": "string"}}, ["id"])
def apagar_lancamento(id: str) -> str:
    x = financas.apagar(id)
    return f"Lançamento apagado: {x['descricao']} ({_reais(x['valor'])})." if x else "Não encontrei esse lançamento."
