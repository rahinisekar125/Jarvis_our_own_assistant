from __future__ import annotations

import logging
from functools import lru_cache

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def get_whisper_model(model: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            local_files_only=True,
        )
    except Exception as exc:  # noqa: BLE001 - first setup may not have the model cached yet.
        LOGGER.warning("Cached Whisper model unavailable; allowing model download: %s", exc)
        return WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
        )
