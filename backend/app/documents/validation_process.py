"""Minimal Linux parser process. No application settings, database or secrets."""

import json
import resource
import sys
import warnings
from io import BytesIO
from typing import TYPE_CHECKING
from xml.etree import ElementTree

if TYPE_CHECKING:
    from PIL import Image


def _has_exact_jpeg_boundary(content: bytes) -> bool:
    """Find real EOI, skipping length-delimited segments and entropy byte stuffing."""
    if not content.startswith(b"\xff\xd8"):
        return False
    offset = 2
    in_scan = False
    while offset < len(content):
        if in_scan:
            offset = content.find(b"\xff", offset)
            if offset < 0:
                return False
        elif content[offset] != 0xFF:
            return False
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset == len(content):
            return False
        marker = content[offset]
        offset += 1
        if in_scan and (marker == 0 or 0xD0 <= marker <= 0xD7):
            continue
        if marker == 0xD9:
            return offset == len(content)
        if marker in {0, 0xD8} or 0xD0 <= marker <= 0xD7:
            return False
        if marker == 1:  # Standalone TEM marker.
            continue
        if offset + 2 > len(content):
            return False
        length = int.from_bytes(content[offset : offset + 2], "big")
        if length < 2 or offset + length > len(content):
            return False
        offset += length
        in_scan = marker == 0xDA
    return False


def _is_apple_gainmap_jpeg(image: "Image.Image", content: bytes, max_pixels: int) -> bool:
    """Recognize a primary JPEG plus Apple HDR auxiliary, not arbitrary MPO pages."""
    from PIL import Image
    from PIL.MpoImagePlugin import MpoImageFile

    if not isinstance(image, MpoImageFile) or image.n_frames != 2:
        return False
    index = image.mpinfo
    if index is None:
        return False
    entries = index.get(0xB002, [])
    if index.get(0xB000) != b"0100" or index.get(0xB001) != 2 or len(entries) != 2:
        return False
    for entry, kind in zip(entries, ("Baseline MP Primary Image", "Undefined"), strict=True):
        attributes = entry["Attribute"]
        if (
            attributes["MPType"] != kind
            or attributes["ImageDataFormat"] != "JPEG"
            or attributes["Reserved"]
            or attributes["DependentParentImageFlag"]
            or attributes["DependentChildImageFlag"]
            or entry["EntryNo1"]
            or entry["EntryNo2"]
        ):
            return False
    primary_bytes = entries[0]["Size"]
    auxiliary_bytes = entries[1]["Size"]
    if (
        entries[0]["DataOffset"] != 0
        or primary_bytes < 4
        or auxiliary_bytes < 4
        or primary_bytes + auxiliary_bytes != len(content)
        or content[primary_bytes - 2 : primary_bytes] != b"\xff\xd9"
        or content[primary_bytes : primary_bytes + 2] != b"\xff\xd8"
        or not content.endswith(b"\xff\xd9")
    ):
        return False
    if not _has_exact_jpeg_boundary(content[:primary_bytes]) or not _has_exact_jpeg_boundary(
        content[primary_bytes:]
    ):
        return False
    width, height = image.size
    if width * height > max_pixels:
        return False
    image.load()
    image.seek(1)
    if image.offset != primary_bytes:
        return False
    # Open the exact auxiliary range independently: no inherited primary XMP,
    # no nested MPO, and no decoder reading beyond its indexed range.
    with Image.open(BytesIO(content[primary_bytes:])) as auxiliary:
        if (
            auxiliary.format != "JPEG"
            or getattr(auxiliary, "n_frames", 1) != 1
            or auxiliary.width > width
            or auxiliary.height > height
            or auxiliary.width * auxiliary.height > max_pixels
        ):
            return False
        xmp = auxiliary.info.get("xmp", b"")
        if not isinstance(xmp, bytes) or len(xmp) > 65533:  # JPEG APP1 segment bound.
            return False
        xml = xmp.decode("utf-8")
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper() or "&" in xml:
            return False
        root = ElementTree.fromstring(xml)
        roles = root.findall(".//{http://ns.apple.com/pixeldatainfo/1.0/}AuxiliaryImageType")
        versions = root.findall(".//{http://ns.apple.com/HDRGainMap/1.0/}HDRGainMapVersion")
        if (
            len(roles) != 1
            or roles[0].text != "urn:com:apple:photo:2020:aux:hdrgainmap"
            or len(versions) != 1
            or versions[0].text != "65536"
        ):
            return False
        auxiliary.verify()
    with Image.open(BytesIO(content[primary_bytes:])) as auxiliary:
        auxiliary.load()
    return True


def _is_heif_container(content: bytes) -> bool:
    """Allow HEIF brands only; pillow-heif can also decode unsupported AVIF."""
    if len(content) < 16 or content[4:8] != b"ftyp":
        return False
    box_size = int.from_bytes(content[:4], "big")
    if box_size < 16 or box_size > len(content):
        return False
    brands = {content[8:12], *[content[index : index + 4] for index in range(16, box_size, 4)]}
    if brands & {b"avif", b"avis"}:
        return False
    return bool(brands & {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"})


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
        if _is_heif_container(content):
            from pillow_heif import open_heif, register_heif_opener

            register_heif_opener(thumbnails=False)
            heif = open_heif(content)
            if heif.primary_index is None or not 0 <= heif.primary_index < len(heif):
                return None
            image = heif[heif.primary_index].to_pillow()
            with image:
                if image.width * image.height > max_pixels:
                    return None
                image.load()
            return "image/heif"
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                fmt = image.format
                if fmt == "MPO":
                    return (
                        "image/jpeg" if _is_apple_gainmap_jpeg(image, content, max_pixels) else None
                    )
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
