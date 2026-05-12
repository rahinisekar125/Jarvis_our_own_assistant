from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(data_dir: Path, verbose: bool = False) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "jarvis.log", encoding="utf-8"),
        ],
    )
