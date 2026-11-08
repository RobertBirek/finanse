"""Bounded local PDF-text child. No application settings, database, HTTP or OCR."""

import json
import math
import resource
import sys
from io import BytesIO


def main() -> None:
    limits = json.loads(sys.argv[1])
    memory = limits["max_memory_bytes"]
    cpu = max(1, math.ceil(limits["timeout_seconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from pypdf import PdfReader

    try:
        content = sys.stdin.buffer.read(limits["max_bytes"] + 1)
        if (
            len(content) > limits["max_bytes"]
            or not content.startswith(b"%PDF-")
            or b"%%EOF" not in content[-1024:]
        ):
            print(json.dumps({"error": "pdf_invalid"}))
            return
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            print(json.dumps({"error": "pdf_encrypted"}))
            return
        pages = []
        size = 0
        for index, page in enumerate(reader.pages):
            if index >= limits["max_pages"]:
                print(json.dumps({"error": "pdf_page_limit"}))
                return
            text = page.extract_text() or ""
            if not text.strip():
                print(json.dumps({"error": "pdf_requires_text"}))
                return
            size += len(text)
            if size > limits["max_text_chars"]:
                print(json.dumps({"error": "pdf_text_limit"}))
                return
            if "\ufffd" in text or "\x00" in text:
                print(json.dumps({"error": "pdf_text_incomplete"}))
                return
            pages.append(text)
        if not pages:
            print(json.dumps({"error": "pdf_requires_text"}))
            return
        print(json.dumps({"pages": pages}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - isolated untrusted parser boundary, no exception data in IPC
        # Untrusted parser boundary: no source text, filenames or tracebacks cross IPC.
        print(json.dumps({"error": "pdf_invalid"}))


if __name__ == "__main__":
    main()
