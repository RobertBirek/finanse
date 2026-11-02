import struct
from io import BytesIO

from PIL import Image
from pypdf import PdfWriter


def valid_pdf_bytes(title: str = "Receipt") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": title})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def valid_png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), color=(12, 34, 56)).save(output, format="PNG")
    return output.getvalue()


def valid_jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), color=(12, 34, 56)).save(output, format="JPEG")
    return output.getvalue()


def valid_heic_bytes() -> bytes:
    import pillow_heif

    output = BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (3, 2), "green")).save(output)
    return output.getvalue()


def apple_gainmap_jpeg_bytes(
    *,
    role: str = "urn:com:apple:photo:2020:aux:hdrgainmap",
    version: str = "65536",
    auxiliary_size: tuple[int, int] = (16, 12),
    extra_frame: bool = False,
    xmp: bytes | None = None,
    corrupt_auxiliary: bool = False,
    primary_trailing: bool = False,
    auxiliary_trailing: bool = False,
) -> bytes:
    """Synthetic MPF-indexed JPEGs, never a private photograph or invoice."""
    exif = Image.Exif()
    exif[274] = 6
    exif[34853] = {1: "N", 2: (52.0, 0.0, 0.0)}
    main = BytesIO()
    Image.new("RGB", (32, 24), "red").save(main, format="JPEG", exif=exif)
    xml = (
        xmp
        if xmp is not None
        else (
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            'xmlns:p="http://ns.apple.com/pixeldatainfo/1.0/" '
            'xmlns:h="http://ns.apple.com/HDRGainMap/1.0/">'
            f"<p:AuxiliaryImageType>{role}</p:AuxiliaryImageType>"
            f"<h:HDRGainMapVersion>{version}</h:HDRGainMapVersion></x:xmpmeta>"
        ).encode()
    )
    aux = BytesIO()
    Image.new("RGB", auxiliary_size, "blue").save(aux, format="JPEG", xmp=xml)
    auxiliary = aux.getvalue()
    if corrupt_auxiliary:
        auxiliary = auxiliary[:32] + b"\xff\xd9"
    frames = [main.getvalue(), auxiliary]
    if primary_trailing:
        frames[0] += b"unindexed-after-real-eoi\xff\xd9"
    if auxiliary_trailing:
        frames[1] += b"unindexed-after-real-eoi\xff\xd9"
    if extra_frame:
        frames.append(aux.getvalue())
    # TIFF header, 3 IFD entries, next-IFD pointer, then 16-byte MP entries.
    entries_offset = 50
    tiff_size = entries_offset + 16 * len(frames)
    marker_size = 8 + tiff_size
    sizes = [len(frames[0]) + marker_size, *map(len, frames[1:])]
    tiff = b"II\x2a\x00" + struct.pack("<I", 8) + struct.pack("<H", 3)
    tiff += struct.pack("<HHI4s", 0xB000, 7, 4, b"0100")
    tiff += struct.pack("<HHII", 0xB001, 4, 1, len(frames))
    tiff += struct.pack("<HHII", 0xB002, 7, 16 * len(frames), entries_offset)
    tiff += struct.pack("<I", 0)
    offset = 0
    for index, size in enumerate(sizes):
        tiff += struct.pack("<IIIHH", 0x030000 if index == 0 else 0, size, offset, 0, 0)
        offset = sum(sizes[: index + 1]) - 10  # TIFF starts at offset10 after JPEG SOI/APP2/MPF.
    marker = b"\xff\xe2" + struct.pack(">H", len(tiff) + 6) + b"MPF\0" + tiff
    return frames[0][:2] + marker + frames[0][2:] + b"".join(frames[1:])
