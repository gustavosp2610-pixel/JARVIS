import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_configure(config):
    # Dados de teste isolados (memória, tokens) — nunca toca nos dados reais.
    import tempfile

    os.environ["JARVIS_PASTA_DADOS"] = tempfile.mkdtemp(prefix="jarvis-teste-")
    os.environ.setdefault("ANTHROPIC_API_KEY", "teste")
