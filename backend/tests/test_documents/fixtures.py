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
