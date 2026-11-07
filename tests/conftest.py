"""Put the project venv's engine first on PATH, so tests never use a stale global one."""
import os
import sys
from pathlib import Path

_venv_bin = Path(sys.executable).parent
if (_venv_bin / "framex").is_file():
    os.environ["PATH"] = os.pathsep.join([str(_venv_bin), os.environ.get("PATH", "")])
