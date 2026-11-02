"""Bounded, non-persistent image normalization for document previews and OCR."""

import asyncio
import json
import sys
from pathlib import Path

from app.config import settings
from app.documents.validation import validation_slots


class ImageNormalizationError(ValueError):
    """Image conversion failed without changing the stored original."""


async def normalize_image(
    content: bytes,
    mime: str,
    *,
    thumbnail: bool = False,
    max_edge: int | None = None,
    max_output_bytes: int | None = None,
) -> bytes:
    """Return a metadata-free JPEG from an admitted document image."""
    if mime not in {"image/jpeg", "image/png", "image/heif"}:
        raise ImageNormalizationError("Unsupported image format")
    if max_edge is not None and max_edge <= 0:
        raise ImageNormalizationError("Image conversion failed")
    if max_output_bytes is not None and max_output_bytes <= 0:
        raise ImageNormalizationError("Image conversion failed")
    slots = validation_slots()
    try:
        await asyncio.wait_for(slots.acquire(), settings.DOCUMENT_VALIDATION_QUEUE_SECONDS)
    except TimeoutError as error:
        raise ImageNormalizationError("Image processing is busy") from error
    try:
        output_bytes = max_output_bytes or settings.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES
        limits = {
            "memory": settings.DOCUMENT_PARSER_MEMORY_BYTES,
            "cpu": settings.DOCUMENT_PARSER_CPU_SECONDS,
            "bytes": settings.DOCUMENT_MAX_FILE_BYTES,
            "pixels": settings.DOCUMENT_MAX_IMAGE_PIXELS,
            "edge": max_edge or settings.DOCUMENT_PREVIEW_MAX_EDGE,
            "resize": max_edge is not None,
            "quality": settings.DOCUMENT_JPEG_QUALITY,
            "output_bytes": output_bytes,
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
            limit=output_bytes + 1,
        )
        assert process.stdin is not None and process.stdout is not None

        async def write_input() -> None:
            assert process.stdin is not None
            try:
                process.stdin.write(content)
                await process.stdin.drain()
            finally:
                process.stdin.close()

        writer = asyncio.create_task(write_input())
        try:
            async with asyncio.timeout(settings.DOCUMENT_PARSER_TIMEOUT_SECONDS):
                output = bytearray()
                while chunk := await process.stdout.read(
                    min(65536, output_bytes + 1 - len(output))
                ):
                    output.extend(chunk)
                    if len(output) > output_bytes:
                        raise ImageNormalizationError("Image conversion failed")
                await writer
                await process.wait()
        except (TimeoutError, BrokenPipeError, ConnectionResetError):
            raise ImageNormalizationError("Image conversion failed") from None
        if process.returncode != 0 or len(output) > output_bytes:
            raise ImageNormalizationError("Image conversion failed")
        if not output.startswith(b"\xff\xd8") or not output.endswith(b"\xff\xd9"):
            raise ImageNormalizationError("Image conversion failed")
        return bytes(output)
    except OSError as error:
        raise ImageNormalizationError("Image conversion unavailable") from error
    finally:
        if "process" in locals() and process.returncode is None:
            process.kill()
        if "writer" in locals():
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
        if "process" in locals():
            # wait() alone can block on a paused stdout transport after an early
            # rejection. The child is stopped; discard its remaining bounded pipe data.
            if process.stdout is not None:
                while await process.stdout.read(65536):
                    pass
            await process.wait()
        slots.release()
