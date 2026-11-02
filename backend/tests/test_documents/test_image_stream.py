"""Exercise the real asyncio pipe boundary, not only the image child converter."""

import asyncio
import base64
import os
import random
import sys
from io import BytesIO

import pytest
from PIL import Image

from app.documents import images


def noise_jpeg(size: tuple[int, int]) -> bytes:
    data = random.Random(1234).randbytes(size[0] * size[1] * 3)
    output = BytesIO()
    Image.frombytes("RGB", size, data).save(output, format="JPEG", quality=94)
    return output.getvalue()


async def child_script(monkeypatch, code: str, *, pipe_limit: int | None = None):
    """Replace only the command, using real OS pipes/processes for all assertions."""
    create = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*_args, **kwargs):
        if pipe_limit is not None:
            kwargs["limit"] = pipe_limit
        process = await create(sys.executable, "-I", "-c", code, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(images.asyncio, "create_subprocess_exec", spawn)
    return processes


def assert_reaped(processes):
    assert len(processes) == 1
    assert processes[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.kill(processes[0].pid, 0)


@pytest.mark.asyncio
async def test_large_real_normalization_matches_complete_child_and_decodes():
    from app.documents.image_process import normalize_image as convert

    original = noise_jpeg((1024, 768))
    expected = convert(
        original,
        "image/jpeg",
        thumbnail=False,
        resize=True,
        max_pixels=images.settings.DOCUMENT_MAX_IMAGE_PIXELS,
        max_edge=1024,
        quality=images.settings.DOCUMENT_JPEG_QUALITY,
    )
    assert len(expected) > 65536
    result = await images.normalize_image(original, "image/jpeg", max_edge=1024)
    assert result == expected
    with Image.open(BytesIO(result)) as image:
        image.load()
        assert image.size == (1024, 768)
        assert image.format == "JPEG" and not image.getexif()


@pytest.mark.asyncio
async def test_delayed_stdout_chunks_are_read_to_eof(monkeypatch):
    original = noise_jpeg((512, 384))
    code = "import sys,time;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data[:8192]);sys.stdout.buffer.flush();time.sleep(.05);sys.stdout.buffer.write(data[8192:])"
    processes = await child_script(monkeypatch, code)
    result = await images.normalize_image(original, "image/jpeg")
    assert result == original
    assert_reaped(processes)


@pytest.mark.asyncio
async def test_writer_and_reader_overlap_to_avoid_pipe_deadlock(monkeypatch):
    expected = noise_jpeg((128, 128))
    code = f"import sys,base64;sys.stdout.buffer.write(base64.b64decode({base64.b64encode(expected)!r}));sys.stdout.buffer.flush();sys.stdin.buffer.read()"
    processes = await child_script(monkeypatch, code, pipe_limit=1024)
    monkeypatch.setattr(images.settings, "DOCUMENT_PARSER_TIMEOUT_SECONDS", 1.0)
    assert await images.normalize_image(b"synthetic-input" * 100_000, "image/jpeg") == expected
    assert_reaped(processes)


@pytest.mark.asyncio
async def test_exact_output_bound_is_allowed(monkeypatch):
    original = noise_jpeg((256, 256))
    processes = await child_script(
        monkeypatch, "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"
    )
    assert (
        await images.normalize_image(original, "image/jpeg", max_output_bytes=len(original))
        == original
    )
    assert_reaped(processes)


@pytest.mark.asyncio
async def test_limit_plus_one_is_rejected_before_waiting_for_eof(monkeypatch):
    code = "import sys,time;sys.stdin.buffer.read();sys.stdout.buffer.write(b'\\xff\\xd8'+b'x'*65536);sys.stdout.buffer.flush();time.sleep(30)"
    processes = await child_script(monkeypatch, code)
    monkeypatch.setattr(images.settings, "DOCUMENT_PARSER_TIMEOUT_SECONDS", 5.0)
    with pytest.raises(images.ImageNormalizationError):
        await asyncio.wait_for(
            images.normalize_image(b"synthetic", "image/jpeg", max_output_bytes=4096), 2
        )
    assert_reaped(processes)


@pytest.mark.parametrize(
    "output,exit_code", [(b"not-jpeg", 0), (b"\xff\xd8truncated", 0), (b"\xff\xd8\xff\xd9", 2)]
)
@pytest.mark.asyncio
async def test_invalid_or_failed_child_output_is_not_published(monkeypatch, output, exit_code):
    processes = await child_script(
        monkeypatch,
        f"import sys;sys.stdin.buffer.read();sys.stdout.buffer.write({output!r});sys.exit({exit_code})",
    )
    with pytest.raises(images.ImageNormalizationError):
        await images.normalize_image(b"synthetic", "image/jpeg")
    assert_reaped(processes)


@pytest.mark.asyncio
async def test_timeout_reaps_child_and_releases_slot(monkeypatch):
    processes = await child_script(monkeypatch, "import time;time.sleep(30)")
    monkeypatch.setattr(images.settings, "DOCUMENT_PARSER_TIMEOUT_SECONDS", 0.15)
    monkeypatch.setattr(images.settings, "DOCUMENT_VALIDATION_CONCURRENCY", 1)
    with pytest.raises(images.ImageNormalizationError):
        await images.normalize_image(b"synthetic" * 100_000, "image/jpeg")
    assert_reaped(processes)
    slot = images.validation_slots()
    await asyncio.wait_for(slot.acquire(), 0.5)
    slot.release()


@pytest.mark.asyncio
async def test_cancellation_reaps_child_writer_and_releases_slot(monkeypatch):
    processes = await child_script(monkeypatch, "import time;time.sleep(30)")
    monkeypatch.setattr(images.settings, "DOCUMENT_VALIDATION_CONCURRENCY", 1)
    task = asyncio.create_task(images.normalize_image(b"synthetic" * 100_000, "image/jpeg"))
    async with asyncio.timeout(2):
        while not processes:
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_reaped(processes)
    slot = images.validation_slots()
    await asyncio.wait_for(slot.acquire(), 0.5)
    slot.release()
