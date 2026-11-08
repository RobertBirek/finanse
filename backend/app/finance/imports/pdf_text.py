"""Bounded pypdf subprocess, separate from invoice OCR and remote AI processing."""

import json
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import settings
from app.finance.imports.errors import ImportError


@dataclass(frozen=True)
class PdfLimits:
    max_bytes: int
    max_pages: int
    max_text_chars: int
    timeout_seconds: float
    max_memory_bytes: int

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in [
                self.max_bytes,
                self.max_pages,
                self.max_text_chars,
                self.max_memory_bytes,
            ]
        ):
            raise ValueError("PDF limits must be positive")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("PDF timeout must be finite and positive")


def configured_pdf_limits() -> PdfLimits:
    return PdfLimits(
        max_bytes=settings.DOCUMENT_MAX_FILE_BYTES,
        max_pages=settings.DOCUMENT_MAX_PAGES,
        max_text_chars=settings.FINANCE_IMPORT_MAX_TEXT_CHARS,
        timeout_seconds=settings.DOCUMENT_PARSER_TIMEOUT_SECONDS,
        max_memory_bytes=settings.DOCUMENT_PARSER_MEMORY_BYTES,
    )


def extract_pdf_pages(content: bytes, limits: PdfLimits) -> tuple[str, ...]:
    if len(content) > limits.max_bytes:
        raise ImportError("source_size_limit", "Plik przekracza skonfigurowany limit.", 413)
    if not content or not content.startswith(b"%PDF-"):
        raise ImportError("pdf_invalid", "Nieprawidłowy dokument PDF.", 422)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).with_name("pdf_text_process.py")),
                json.dumps(asdict(limits)),
            ],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            timeout=limits.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ImportError("pdf_timeout", "Odczyt PDF przekroczył limit czasu.", 422) from error
    if result.returncode != 0:
        raise ImportError("pdf_resource_limit", "Nie udało się bezpiecznie odczytać PDF.", 422)
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict) and data.get("error") in {
            "pdf_invalid",
            "pdf_encrypted",
            "pdf_requires_text",
            "pdf_page_limit",
            "pdf_text_limit",
            "pdf_text_incomplete",
        }:
            raise ImportError(
                data["error"], "PDF wymaga poprawnego, pełnego tekstowego oryginału.", 422
            )
        pages = data["pages"]
        if not isinstance(pages, list) or not pages or len(pages) > limits.max_pages:
            raise ValueError("invalid page result")
        if any(not isinstance(page, str) or not page.strip() for page in pages):
            raise ValueError("invalid text result")
        if sum(map(len, pages)) > limits.max_text_chars:
            raise ValueError("invalid result size")
        return tuple(pages)
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, ImportError):
            raise
        raise ImportError("pdf_invalid", "Nie udało się bezpiecznie odczytać PDF.", 422) from error
