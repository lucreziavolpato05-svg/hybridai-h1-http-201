"""Put the project venv's engine first on PATH, so tests never use a stale global one."""
import os

from runtime.query import venv_engine

_engine = venv_engine()
if _engine is not None:
    os.environ["PATH"] = os.pathsep.join([str(_engine.parent), os.environ.get("PATH", "")])
