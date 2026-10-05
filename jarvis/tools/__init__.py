"""Registro de ferramentas do JARVIS.

Cada ferramenta é uma função Python comum registrada com o decorador ``@ferramenta``.
O registro guarda o schema JSON enviado ao Claude e o nível de risco:

- ``seguro``: executa direto (abrir programa, ler e-mails, ver agenda...).
- ``confirmar``: o JARVIS pede autorização antes (enviar e-mail, apagar arquivo, desligar...).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

SEGURO = "seguro"
CONFIRMAR = "confirmar"


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any]
    obrigatorios: list[str]
    risco: str
    funcao: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.nome,
            "description": self.descricao,
            "input_schema": {
                "type": "object",
                "properties": self.parametros,
                "required": self.obrigatorios,
                "additionalProperties": False,
            },
        }

    def resumo(self, entrada: dict[str, Any]) -> str:
        """Texto curto descrevendo a ação, usado no pedido de confirmação."""
        args = ", ".join(f"{k}={v!r}" for k, v in entrada.items())
        return f"{self.nome}({args})"


REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(
    nome: str,
    descricao: str,
    parametros: dict[str, Any] | None = None,
    obrigatorios: list[str] | None = None,
    risco: str = SEGURO,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorador(funcao: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRO[nome] = Ferramenta(
            nome=nome,
            descricao=descricao,
            parametros=parametros or {},
            obrigatorios=obrigatorios or [],
            risco=risco,
            funcao=funcao,
        )
        return funcao

    return decorador


def schemas() -> list[dict[str, Any]]:
    """Schemas em ordem estável (ordem fixa mantém o cache de prompt válido)."""
    return [REGISTRO[nome].schema() for nome in sorted(REGISTRO)]


def executar(nome: str, entrada: dict[str, Any]) -> str:
    """Executa a ferramenta e devolve sempre texto. Erros viram mensagem, não exceção."""
    f = REGISTRO.get(nome)
    if f is None:
        raise KeyError(f"Ferramenta desconhecida: {nome}")
    faltando = [p for p in f.obrigatorios if p not in entrada]
    if faltando:
        raise ValueError(f"Parâmetros obrigatórios ausentes: {', '.join(faltando)}")
    extras = [p for p in entrada if p not in f.parametros]
    if extras:
        raise ValueError(f"Parâmetros desconhecidos: {', '.join(extras)}")
    resultado = f.funcao(**entrada)
    if isinstance(resultado, str):
        return resultado
    return json.dumps(resultado, ensure_ascii=False, default=str)


def carregar_todas() -> None:
    """Importa os módulos de ferramentas para que se registrem."""
    from jarvis import memory, rotinas, tarefas  # noqa: F401
    from jarvis.tools import computer, dia_a_dia, estudos, financas, google, organizar, whatsapp  # noqa: F401
