"""Testes das utilidades: Gemini estável, rotinas, estudos, finanças, dia a dia e organizar o PC."""

import json
import os
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from jarvis import tools
from jarvis.cerebro_gemini import CerebroGemini
from jarvis.rotinas import EXEMPLOS, Rotinas
from jarvis.tools import dia_a_dia, estudos, organizar
from jarvis.tools.financas import Financas
from tests.test_gemini import ControleFalso, api_falsa, ok  # noqa: F401 (fixture)

ERRO_503 = (503, {"error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}})


# ---------------------------------------------------------------------------
# Gemini: novas tentativas e modelo reserva
# ---------------------------------------------------------------------------


def test_gemini_tenta_de_novo_quando_sobrecarregado(api_falsa, caplog):  # noqa: F811
    api = api_falsa([ERRO_503, ERRO_503, ok({"text": "Agora foi."})])
    esperas = []
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    c._esperar = lambda s: esperas.append(s) or False
    assert c.responder("oi") == "Agora foi."
    assert esperas == [2, 4]
    assert "503" in caplog.text


def test_gemini_usa_modelo_reserva(api_falsa):  # noqa: F811
    api = api_falsa([ERRO_503] * 4 + [ok({"text": "Respondi com o reserva."})])
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    c._esperar = lambda s: False
    assert c.responder("oi") == "Respondi com o reserva."
    assert "flash-lite" in api.pedidos[-1]["path"] and "flash-lite" not in api.pedidos[0]["path"]


def test_gemini_desiste_com_mensagem_e_nao_tenta_erro_permanente(api_falsa):  # noqa: F811
    api = api_falsa([ERRO_503] * 6)
    c = CerebroGemini(lambda r: True, cliente=api.cliente, controle_pc=ControleFalso())
    c._esperar = lambda s: False
    assert "instáveis" in c.responder("oi") and len(api.pedidos) == 6
    api2 = api_falsa([(400, {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}})])
    c2 = CerebroGemini(lambda r: True, cliente=api2.cliente, controle_pc=ControleFalso())
    assert "chave" in c2.responder("oi") and len(api2.pedidos) == 1


# ---------------------------------------------------------------------------
# Rotinas
# ---------------------------------------------------------------------------


def test_rotinas_exemplos_criar_executar_apagar(tmp_path):
    r = Rotinas(tmp_path / "rotinas.json")
    assert set(r.nomes()) == set(EXEMPLOS)  # primeira vez cria os exemplos
    r.salvar("Modo Jogo", ["abrir a Steam", "volume em 70"])
    assert r.achar("modo jogo")[1] == ["abrir a Steam", "volume em 70"]
    assert r.achar("rotina modo jogo")[0] == "modo jogo"
    r.salvar("modo jogo", ["abrir o Discord"])  # substitui
    assert r.achar("Modo Jogo")[1] == ["abrir o Discord"]
    assert r.apagar("modo jogo") == "modo jogo" and r.achar("modo jogo") is None
    with pytest.raises(ValueError):
        r.salvar("vazia", [])


def test_executar_rotina_devolve_passos_numerados(monkeypatch, tmp_path):
    from jarvis import rotinas as mod

    monkeypatch.setattr(mod, "rotinas", Rotinas(tmp_path / "r.json"))
    texto = mod.executar_rotina("bom dia")
    assert "Execute AGORA" in texto and "1. " in texto
    assert "Não existe" in mod.executar_rotina("rotina inexistente")


def test_contexto_inclui_rotinas_na_primeira_mensagem():
    from jarvis.contexto import contexto_usuario

    assert "Rotinas salvas" in contexto_usuario(True)
    assert "Rotinas salvas" not in contexto_usuario(False)


# ---------------------------------------------------------------------------
# Estudos
# ---------------------------------------------------------------------------


def test_ler_documento_pdf_docx_txt(tmp_path, monkeypatch):
    import zipfile

    from pypdf import PdfWriter

    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        "<w:p><w:r><w:t>Fotossíntese transforma </w:t></w:r><w:r><w:t>luz em energia.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Segundo parágrafo</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(tmp_path / "aula.docx", "w") as z:
        z.writestr("word/document.xml", xml)
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(tmp_path / "vazio.pdf", "wb") as f:
        w.write(f)
    (tmp_path / "notas.md").write_text("# Revisão\nItem 1", encoding="utf-8")
    monkeypatch.setenv("JARVIS_PASTAS_PERMITIDAS", str(tmp_path))
    assert estudos.ler_documento(str(tmp_path / "aula.docx")) == "Fotossíntese transforma luz em energia.\nSegundo parágrafo"
    assert "não tem texto legível" in estudos.ler_documento(str(tmp_path / "vazio.pdf"))
    assert "Revisão" in estudos.ler_documento(str(tmp_path / "notas.md"))
    with pytest.raises(ValueError):
        estudos.extrair_texto(tmp_path / "x.xyz")


def test_texto_de_html_ignora_scripts():
    titulo, texto = estudos.texto_de_html(
        "<html><head><title>Artigo</title><script>var x=1</script></head>"
        "<body><nav>Menu</nav><h1>Título</h1><p>Primeiro parágrafo.</p><p>Segundo.</p></body></html>"
    )
    assert titulo == "Artigo"
    assert texto == "Título\nPrimeiro parágrafo.\nSegundo."


def test_anotacoes(tmp_path, monkeypatch):
    monkeypatch.setattr(estudos, "PASTA_ANOTACOES", tmp_path / "Anotações")
    assert "salva" in estudos.salvar_anotacao("Flashcards: História", "P: Quem descobriu o Brasil?")
    assert "acrescentado" in estudos.salvar_anotacao("Flashcards: História", "P: Em que ano?")
    assert "Flashcards História" in estudos.listar_anotacoes()
    conteudo = estudos.ler_anotacao("história")
    assert "Quem descobriu" in conteudo and "Em que ano" in conteudo


def test_pomodoro_cria_lembretes(monkeypatch, tmp_path):
    from jarvis import tarefas as mod

    lista = mod.Tarefas(tmp_path / "t.json")
    monkeypatch.setattr(mod, "tarefas", lista)
    r = estudos.pomodoro(25, 5, 2)
    msgs = [lem["mensagem"] for lem in lista.lembretes()]
    assert msgs == ["Fim do foco 1 de 2. Pausa de 5 minutos.", "Fim da pausa. Hora do foco 2 de 2.", "Pomodoro concluído! Bom trabalho."]
    assert "2 ciclo(s)" in r


# ---------------------------------------------------------------------------
# Finanças
# ---------------------------------------------------------------------------


def test_financas_lancar_resumir_apagar(tmp_path):
    f = Financas(tmp_path / "f.json")
    f.lancar("gasto", 30, "mercado", "mercado")
    f.lancar("gasto", 12.5, "uber", "transporte")
    f.lancar("gasto", -20, "padaria", "mercado")  # sinal é ignorado
    f.lancar("receita", 100, "pix do João")
    f.lancar("gasto", 999, "mês passado", "lazer", "2001-01-10")
    r = f.resumo()
    assert r["gastos"] == 62.5 and r["receitas"] == 100 and r["saldo"] == 37.5
    assert r["categorias"][0] == ("mercado", 50.0)
    assert f.resumo("01/2001")["gastos"] == 999
    item = f.do_mes()[0]
    assert f.apagar(item["id"])["id"] == item["id"] and f.apagar("nada") is None
    with pytest.raises(ValueError):
        f.lancar("gasto", 0, "nada")


def test_ferramenta_registrar_gasto_responde_em_reais(monkeypatch, tmp_path):
    from jarvis.tools import financas as mod

    monkeypatch.setattr(mod, "financas", Financas(tmp_path / "f.json"))
    assert "R$ 1.234,50" in mod.registrar_gasto(1234.5, "notebook", "compras")
    assert "compras: R$ 1.234,50" in mod.resumo_financeiro()


# ---------------------------------------------------------------------------
# Dia a dia (HTTP simulado)
# ---------------------------------------------------------------------------


def test_previsao_do_tempo(monkeypatch):
    respostas = {
        "geocoding": {"results": [{"name": "São Paulo", "latitude": -23.5, "longitude": -46.6}]},
        "forecast": {
            "current": {"temperature_2m": 24.4, "apparent_temperature": 25.1, "weather_code": 2, "wind_speed_10m": 10},
            "daily": {"time": ["2026-10-05"], "weather_code": [61], "temperature_2m_max": [28], "temperature_2m_min": [17],
                      "precipitation_probability_max": [70]},
        },
    }
    monkeypatch.setattr(dia_a_dia, "_json", lambda url: respostas["geocoding" if "geocoding" in url else "forecast"])
    texto = dia_a_dia.previsao_do_tempo("São Paulo", 1)
    assert "São Paulo agora: 24°C" in texto and "chuva fraca" in texto and "chuva 70%" in texto


def test_cotacao(monkeypatch):
    monkeypatch.setattr(dia_a_dia, "_json", lambda url: {"USDBRL": {"name": "Dólar Americano/Real Brasileiro", "bid": "5.4321", "pctChange": "-0.5"}})
    texto = dia_a_dia.cotacao("usd, xyz")
    assert "R$ 5,43 (-0.50% hoje)" in texto and "XYZ: cotação não encontrada" in texto


def test_noticias(monkeypatch):
    rss = b"""<rss><channel><item><title>Chuva forte em SP - G1</title><source>G1</source></item>
    <item><title>Selic cai</title></item></channel></rss>"""
    urls = []
    monkeypatch.setattr(dia_a_dia, "_baixar", lambda url: urls.append(url) or rss)
    texto = dia_a_dia.noticias("economia")
    assert texto == "- Chuva forte em SP (G1)\n- Selic cai"
    assert "search?q=economia" in urls[0]


# ---------------------------------------------------------------------------
# Organizar o PC
# ---------------------------------------------------------------------------


def test_organizar_pasta_sem_sobrescrever(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_PASTAS_PERMITIDAS", str(tmp_path))
    for nome in ("foto.jpg", "nota.pdf", "setup.exe", "musica.mp3", "coisa.xyz", "baixando.crdownload"):
        (tmp_path / nome).write_text("x")
    (tmp_path / "Imagens").mkdir()
    (tmp_path / "Imagens" / "foto.jpg").write_text("antiga")
    plano = organizar.planejar_organizacao(str(tmp_path))
    assert "Imagens: 1" in plano and "Outros: 1" in plano and "crdownload" not in plano
    r = organizar.organizar_pasta(str(tmp_path))
    assert "Pasta organizada" in r
    assert (tmp_path / "Imagens" / "foto.jpg").read_text() == "antiga"
    assert (tmp_path / "Imagens" / "foto (2).jpg").exists()
    assert (tmp_path / "Documentos" / "nota.pdf").exists() and (tmp_path / "Instaladores" / "setup.exe").exists()
    assert (tmp_path / "baixando.crdownload").exists()  # download em andamento fica
    assert tools.REGISTRO["organizar_pasta"].risco == tools.CONFIRMAR


def test_organizar_fora_das_pastas_permitidas_e_bloqueado():
    with pytest.raises(PermissionError):
        organizar.planejar_organizacao("/etc")


def test_analisar_e_arquivos_grandes(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_PASTAS_PERMITIDAS", str(tmp_path))
    (tmp_path / "grande.mp4").write_bytes(b"0" * (2 * 1024 * 1024))
    (tmp_path / "pequeno.txt").write_text("oi")
    assert "Vídeos 1" in organizar.analisar_pasta(str(tmp_path))
    assert "grande.mp4" in organizar.arquivos_grandes(str(tmp_path), 1)
    assert "Nenhum arquivo" in organizar.arquivos_grandes(str(tmp_path), 50)


def test_limpar_temporarios_so_apaga_antigos(tmp_path):
    antigo, novo = tmp_path / "antigo.tmp", tmp_path / "novo.tmp"
    antigo.write_bytes(b"x" * 100)
    novo.write_bytes(b"y")
    velho = time.time() - 5 * 86400
    os.utime(antigo, (velho, velho))
    (tmp_path / "sub").mkdir()
    qtd, liberado = organizar.limpar_pasta_antiga(tmp_path)
    assert (qtd, liberado) == (1, 100)
    assert not antigo.exists() and novo.exists() and not (tmp_path / "sub").exists()
