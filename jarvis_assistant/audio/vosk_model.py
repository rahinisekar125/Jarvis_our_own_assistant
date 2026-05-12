from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=2)
def get_vosk_model(model_path: str):
    from vosk import Model, SetLogLevel

    path = Path(model_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise RuntimeError(f"Vosk model not found: {path}")

    SetLogLevel(-1)
    return Model(str(path))
