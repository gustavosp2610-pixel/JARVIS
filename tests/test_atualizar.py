"""Atualização automática: troca só os arquivos do programa e preserva dados, chaves e bibliotecas."""

import io
import json
import zipfile

import pytest

from jarvis import atualizar


def zip_com(arquivos: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("JARVIS-ramo/", "")
        for nome, conteudo in arquivos.items():
            z.writestr(f"JARVIS-ramo/{nome}", conteudo)
    return buf.getvalue()


@pytest.fixture
def instalacao(tmp_path, monkeypatch):
    raiz = tmp_path / "JARVIS"
    (raiz / "jarvis").mkdir(parents=True)
    (raiz / "dados").mkdir()
    (raiz / "jarvis" / "main.py").write_text("versao antiga")
    (raiz / ".env").write_text("GEMINI_API_KEY=minha-chave")
    (raiz / "dados" / "tarefas.json").write_text('{"tarefas": ["minha"]}')
    (raiz / "requirements.txt").write_text("rich\n")
    (raiz / "iniciar_jarvis.bat").write_text("@echo off\r\npython -m jarvis\r\npause\r\n")  # formato antigo
    (raiz / "conectar_gmail.bat").write_text("@echo off\r\nrem JARVIS-BAT-SEGURO\r\nvelho\r\n")
    monkeypatch.setattr(atualizar.config, "pasta_dados", raiz / "dados")
    monkeypatch.delenv("JARVIS_ATUALIZAR_SOZINHO", raising=False)
    return raiz


NOVA = {
    "jarvis/main.py": "versao nova",
    "jarvis/novo_modulo.py": "oi",
    ".env": "GEMINI_API_KEY=do-github",
    "dados/tarefas.json": "{}",
    "requirements.txt": "rich\n",
    "iniciar_jarvis.bat": "@echo off\r\nrem JARVIS-BAT-SEGURO\r\nnovo\r\n",
    "conectar_gmail.bat": "@echo off\r\nrem JARVIS-BAT-SEGURO\r\nnovo\r\n",
}


def test_aplica_sem_tocar_em_dados_chaves_e_bat_antigo(instalacao):
    alterados = atualizar.aplicar_zip(zip_com(NOVA), instalacao)
    assert (instalacao / "jarvis" / "main.py").read_text() == "versao nova"
    assert (instalacao / "jarvis" / "novo_modulo.py").exists()
    assert (instalacao / ".env").read_text() == "GEMINI_API_KEY=minha-chave"
    assert (instalacao / "dados" / "tarefas.json").read_text() == '{"tarefas": ["minha"]}'
    assert "python -m jarvis" in (instalacao / "iniciar_jarvis.bat").read_text()  # antigo, pode estar rodando
    assert "novo" in (instalacao / "conectar_gmail.bat").read_text()  # já é do formato seguro
    assert sorted(alterados) == ["conectar_gmail.bat", "jarvis/main.py", "jarvis/novo_modulo.py"]
    assert not list(instalacao.rglob("*.novo"))


def test_atualiza_quando_ha_versao_nova_e_lembra(instalacao, monkeypatch):
    monkeypatch.setattr(atualizar, "versao_remota", lambda: ("abc123", "Gmail com senha de app"))
    monkeypatch.setattr(atualizar, "baixar_zip", lambda: zip_com(NOVA))
    pips = []
    monkeypatch.setattr(atualizar, "instalar_bibliotecas", lambda d: pips.append(d) or True)
    avisos = []
    assert atualizar.atualizar_se_preciso(avisos.append, instalacao) is True
    assert avisos[0] == "Baixando atualização: Gmail com senha de app"
    assert pips == []  # requirements igual: não reinstala
    assert json.loads((instalacao / "dados" / "versao.json").read_text())["sha"] == "abc123"
    assert atualizar.atualizar_se_preciso(avisos.append, instalacao) is False  # já está na versão


def test_requirements_mudou_instala_bibliotecas(instalacao, monkeypatch):
    monkeypatch.setattr(atualizar, "versao_remota", lambda: ("def456", "Nova biblioteca"))
    monkeypatch.setattr(atualizar, "baixar_zip", lambda: zip_com({**NOVA, "requirements.txt": "rich\npypdf\n"}))
    pips = []
    monkeypatch.setattr(atualizar, "instalar_bibliotecas", lambda d: pips.append(d) or True)
    atualizar.atualizar_se_preciso(lambda t: None, instalacao)
    assert pips == [instalacao]


def test_sem_internet_abre_normal(instalacao, monkeypatch):
    def sem_rede():
        raise OSError("sem internet")

    monkeypatch.setattr(atualizar, "versao_remota", sem_rede)
    assert atualizar.atualizar_se_preciso(lambda t: None, instalacao) is False
    assert (instalacao / "jarvis" / "main.py").read_text() == "versao antiga"


def test_pode_desligar(instalacao, monkeypatch):
    monkeypatch.setenv("JARVIS_ATUALIZAR_SOZINHO", "false")
    monkeypatch.setattr(atualizar, "versao_remota", lambda: pytest.fail("não deveria consultar"))
    assert atualizar.atualizar_se_preciso(lambda t: None, instalacao) is False


def test_bats_do_repositorio_sao_seguros_para_atualizar():
    from jarvis.config import RAIZ

    for bat in RAIZ.glob("*.bat"):
        conteudo = bat.read_bytes()
        assert b"JARVIS-BAT-SEGURO" in conteudo and b"\r\n" in conteudo, bat.name
    linha = [l for l in (RAIZ / "iniciar_jarvis.bat").read_text().splitlines() if "-m jarvis" in l and "--configurar" not in l][0]
    assert linha.endswith("& pause & exit /b 0")  # tudo numa linha: trocar o arquivo depois não quebra o cmd
