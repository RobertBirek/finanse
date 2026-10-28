"""Bounded, non-persistent image normalization for document previews and OCR."""

import asyncio
import json
import sys
from pathlib import Path

from app.config import settings
from app.documents.validation import validation_slots


class ImageNormalizationError(ValueError):
    """Image conversion failed without changing the stored original."""


async def normalize_image(content: bytes, mime: str, *, thumbnail: bool = False) -> bytes:
    """Return a metadata-free JPEG from an admitted document image."""
    if mime not in {"image/jpeg", "image/png", "image/heif"}:
        raise ImageNormalizationError("Unsupported image format")
    slots = validation_slots()
    try:
        await asyncio.wait_for(slots.acquire(), settings.DOCUMENT_VALIDATION_QUEUE_SECONDS)
    except TimeoutError as error:
        raise ImageNormalizationError("Image processing is busy") from error
    try:
        limits = {
            "memory": settings.DOCUMENT_PARSER_MEMORY_BYTES,
            "cpu": settings.DOCUMENT_PARSER_CPU_SECONDS,
            "bytes": settings.DOCUMENT_MAX_FILE_BYTES,
            "pixels": settings.DOCUMENT_MAX_IMAGE_PIXELS,
            "edge": settings.DOCUMENT_PREVIEW_MAX_EDGE,
            "quality": settings.DOCUMENT_JPEG_QUALITY,
            "output_bytes": settings.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES,
            "mime": mime,
            "thumbnail": thumbnail,
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(Path(__file__).with_name("image_process.py")),
            json.dumps(limits),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            cwd="/",
            limit=settings.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES + 1,
        )
        assert process.stdin is not None and process.stdout is not None
        try:
            async with asyncio.timeout(settings.DOCUMENT_PARSER_TIMEOUT_SECONDS):
                process.stdin.write(content)
                await process.stdin.drain()
                process.stdin.close()
                output = await process.stdout.read(settings.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES + 1)
                await process.wait()
        except (TimeoutError, BrokenPipeError, ConnectionResetError) as error:
            raise ImageNormalizationError("Image conversion failed") from error
        if process.returncode != 0 or len(output) > settings.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES:
            raise ImageNormalizationError("Image conversion failed")
        if not output.startswith(b"\xff\xd8"):
            raise ImageNormalizationError("Image conversion failed")
        return output
    except OSError as error:
        raise ImageNormalizationError("Image conversion unavailable") from error
    finally:
        if "process" in locals() and process.returncode is None:
            process.kill()
        if "process" in locals():
            await process.wait()
        slots.release()
