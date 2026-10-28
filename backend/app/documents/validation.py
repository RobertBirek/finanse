"""Resource bounded validation. This is not a filesystem/network sandbox."""

import asyncio
import json
import sys
import weakref
from pathlib import Path

from app.config import settings


class UnsupportedDocumentFormatError(ValueError):
    """Invalid, excessive or unparseable document."""


class DocumentValidationUnavailableError(Exception):
    """Parser admission or process creation unavailable; safe to retry upload."""


_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def validation_slots() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(settings.DOCUMENT_VALIDATION_CONCURRENCY)
    return _slots[loop]


async def run_validation_process(command: list[str], content: bytes, timeout: float) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        cwd="/",
        limit=4096,
    )
    assert process.stdin is not None and process.stdout is not None

    async def write_input() -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(content)
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    writer = asyncio.create_task(write_input())
    try:
        async with asyncio.timeout(timeout):
            output = await process.stdout.read(4097)
            if len(output) > 4096:
                raise UnsupportedDocumentFormatError("Document validation failed")
            # read() may return a partial pipe write; bound the remainder too.
            output += await process.stdout.read(4097 - len(output))
            if len(output) > 4096:
                raise UnsupportedDocumentFormatError("Document validation failed")
            await writer
            await process.wait()
            if process.returncode != 0:
                raise UnsupportedDocumentFormatError("Document validation failed")
            result = json.loads(output)
            mime = result.get("mime") if isinstance(result, dict) else None
            if mime not in {"application/pdf", "image/png", "image/jpeg", "image/heif"}:
                raise UnsupportedDocumentFormatError("Unsupported document format")
            return str(mime)
    except (TimeoutError, json.JSONDecodeError, UnicodeError) as error:
        raise UnsupportedDocumentFormatError("Document validation failed") from error
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)


async def validate_document_content(content: bytes, declared_mime: str) -> str:
    if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
        raise UnsupportedDocumentFormatError("Document exceeds file size limit")
    slots = validation_slots()
    try:
        await asyncio.wait_for(slots.acquire(), settings.DOCUMENT_VALIDATION_QUEUE_SECONDS)
    except TimeoutError as error:
        raise DocumentValidationUnavailableError from error
    try:
        limits = {
            "memory": settings.DOCUMENT_PARSER_MEMORY_BYTES,
            "cpu": settings.DOCUMENT_PARSER_CPU_SECONDS,
            "bytes": settings.DOCUMENT_MAX_FILE_BYTES,
            "pages": settings.DOCUMENT_MAX_PAGES,
            "pixels": settings.DOCUMENT_MAX_IMAGE_PIXELS,
        }
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).with_name("validation_process.py")),
            json.dumps(limits),
        ]
        try:
            mime = await run_validation_process(
                command, content, settings.DOCUMENT_PARSER_TIMEOUT_SECONDS
            )
        except OSError as error:
            raise DocumentValidationUnavailableError from error
        aliases = {"image/heic": "image/heif", "image/heif": "image/heif"}
        normalized_declared_mime = aliases.get(declared_mime, declared_mime)
        if (
            declared_mime not in {"", "application/octet-stream"}
            and mime != normalized_declared_mime
        ):
            raise UnsupportedDocumentFormatError("Unsupported document format or MIME mismatch")
        return mime
    finally:
        slots.release()
