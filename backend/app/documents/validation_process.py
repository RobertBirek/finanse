"""Minimal Linux parser process. No application settings, database or secrets."""

import json
import resource
import sys
import warnings
from io import BytesIO


def detect_document_mime_type(
    content: bytes, max_pages: int = 100, max_pixels: int = 25_000_000
) -> str | None:
    from PIL import Image
    from pypdf import PdfReader

    try:
        if content.startswith(b"%PDF-"):
            if b"%%EOF" not in content[-1024:]:
                return None
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                return None
            # Iterate with a bound rather than materializing every page.
            count = 0
            for _ in reader.pages:
                count += 1
                if count > max_pages:
                    return None
            return "application/pdf" if count else None
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                fmt = image.format
                if fmt not in {"PNG", "JPEG"} or getattr(image, "n_frames", 1) != 1:
                    return None
                if image.width * image.height > max_pixels:
                    return None
                if fmt == "PNG" and not content.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
                    return None
                if fmt == "JPEG" and not content.endswith(b"\xff\xd9"):
                    return None
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
        return {"PNG": "image/png", "JPEG": "image/jpeg"}[fmt]
    except Exception:  # noqa: BLE001 - untrusted parser boundary, no exception data crosses IPC
        return None


def main() -> None:
    limits = json.loads(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory"], limits["memory"]))
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    content = sys.stdin.buffer.read(limits["bytes"] + 1)
    mime = (
        None
        if len(content) > limits["bytes"]
        else detect_document_mime_type(content, limits["pages"], limits["pixels"])
    )
    print(json.dumps({"mime": mime}))


if __name__ == "__main__":
    main()
