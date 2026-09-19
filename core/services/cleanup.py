# core/services/cleanup.py
"""Service layer for clearing downloads, the vector store, and analysis cache."""

from typing import Optional

from utils.audio_processor import clear_download_dir
from core.vector_store import clear_vector_store
from core.analyzer import clear_analyzer_cache


def clear_all(preserve_file: Optional[str] = None) -> None:
    """Clear downloaded files, vector DB, and in-memory analysis cache.

    Args:
        preserve_file: Absolute path of a file that should **not** be
                       deleted from the download directory.
    """
    clear_download_dir(preserve_file=preserve_file)
    clear_vector_store()
    clear_analyzer_cache()
