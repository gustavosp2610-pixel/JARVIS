"""Dia a dia: previsão do tempo, cotações e notícias — tudo grátis e sem chave."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from jarvis.config import config
from jarvis.tools import ferramenta

TEMPO_LIMITE = 12


def _baixar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as resp:
        return resp.read()


def _json(url: str) -> Any:
    return json.loads(_baixar(url).decode("utf-8"))


# Códigos de tempo da Open-Meteo (WMO)
_CONDICOES = {
    0: "céu limpo", 1: "quase limpo", 2: "parcialmente nublado", 3: "nublado", 45: "neblina", 48: "neblina",
    51: "garoa fraca", 53: "garoa", 55: "garoa forte", 61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    66: "chuva congelante", 67: "chuva congelante", 71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva", 82: "pancadas de chuva fortes",
    95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo",
}


@ferramenta(
    "previsao_do_tempo",
    "Previsão do tempo de agora e dos próximos dias (temperatura, chance de chuva).",
    {
        "cidade": {"type": "string", "description": "Padrão: a cidade do usuário."},
        "dias": {"type": "integer", "description": "1 a 7. Padrão 3."},
    },
)
def previsao_do_tempo(cidade: str | None = None, dias: int | None = None) -> str:
    cidade = (cidade or config.cidade or "").strip()
    if not cidade:
        return "Não sei a cidade do usuário. Pergunte e, se ele quiser, use lembrar para guardar."
    geo = _json(
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": cidade.split(",")[0], "count": 1, "language": "pt", "format": "json"})
    )
    if not geo.get("results"):
        return f"Não encontrei a cidade '{cidade}'."
    lugar = geo["results"][0]
    n = max(1, min(7, int(dias or 3)))
    prev = _json(
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode(
            {
                "latitude": lugar["latitude"],
                "longitude": lugar["longitude"],
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": n,
            }
        )
    )
    atual = prev["current"]
    linhas = [
        f"{lugar['name']} agora: {atual['temperature_2m']:.0f}°C (sensação {atual['apparent_temperature']:.0f}°C), "
        f"{_CONDICOES.get(atual['weather_code'], 'tempo variável')}, vento {atual['wind_speed_10m']:.0f} km/h."
    ]
    d = prev["daily"]
    for i, dia in enumerate(d["time"]):
        linhas.append(
            f"{dia}: {_CONDICOES.get(d['weather_code'][i], 'variável')}, mín {d['temperature_2m_min'][i]:.0f}°C, "
            f"máx {d['temperature_2m_max'][i]:.0f}°C, chuva {d['precipitation_probability_max'][i] or 0}%."
        )
    return "\n".join(linhas)


@ferramenta(
    "cotacao",
    "Cotação atual de moedas e cripto em reais (dólar, euro, libra, bitcoin, ethereum...).",
    {"moedas": {"type": "string", "description": "Códigos separados por vírgula, ex.: 'USD,EUR,BTC'. Padrão: USD,EUR,BTC."}},
)
def cotacao(moedas: str | None = None) -> str:
    codigos = [c.strip().upper() for c in (moedas or "USD,EUR,BTC").replace(" ", ",").split(",") if c.strip()]
    pares = ",".join(f"{c}-BRL" for c in codigos[:8])
    dados = _json(f"https://economia.awesomeapi.com.br/json/last/{pares}")
    linhas = []
    for c in codigos[:8]:
        item = dados.get(f"{c}BRL")
        if not item:
            linhas.append(f"{c}: cotação não encontrada.")
            continue
        valor = float(item["bid"])
        variacao = float(item.get("pctChange") or 0)
        texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        linhas.append(f"{item.get('name', c)}: R$ {texto} ({variacao:+.2f}% hoje)")
    return "\n".join(linhas)


@ferramenta(
    "noticias",
    "Manchetes de agora do Google Notícias (Brasil), gerais ou sobre um tema.",
    {
        "tema": {"type": "string", "description": "Opcional, ex.: 'futebol', 'tecnologia', 'Flamengo'."},
        "quantidade": {"type": "integer", "description": "Padrão 6, máximo 15."},
    },
)
def noticias(tema: str | None = None, quantidade: int | None = None) -> str:
    base = "https://news.google.com/rss"
    sufixo = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
    url = f"{base}/search?q={urllib.parse.quote(tema)}&{sufixo}" if tema else f"{base}?{sufixo}"
    raiz = ET.fromstring(_baixar(url))
    itens = raiz.findall("./channel/item")[: max(1, min(15, int(quantidade or 6)))]
    if not itens:
        return "Não encontrei notícias agora."
    linhas = []
    for it in itens:
        titulo = (it.findtext("title") or "").strip()
        fonte = (it.findtext("source") or "").strip()
        if fonte and titulo.endswith(f" - {fonte}"):
            titulo = titulo[: -len(fonte) - 3]
        linhas.append(f"- {titulo}" + (f" ({fonte})" if fonte else ""))
    return "\n".join(linhas)
