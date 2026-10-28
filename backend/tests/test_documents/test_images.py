from io import BytesIO

import pytest
from PIL import Image


def jpeg_with_orientation_and_gps() -> bytes:
    image = Image.new("RGB", (2, 4), "red")
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


@pytest.mark.asyncio
async def test_orientation_without_gps():
    from app.documents.images import normalize_image

    result = await normalize_image(jpeg_with_orientation_and_gps(), "image/jpeg")

    assert result.startswith(b"\xff\xd8")
    with Image.open(BytesIO(result)) as image:
        assert image.size == (4, 2)
        assert image.getexif().get(34853) is None


@pytest.mark.asyncio
async def test_conversion_timeout_keeps_saved_original(monkeypatch, tmp_path):
    from app.documents import images, service

    original = jpeg_with_orientation_and_gps()
    digest = service.compute_sha256(original)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    service._write_document_content(digest, original)
    monkeypatch.setattr(images.settings, "DOCUMENT_PARSER_TIMEOUT_SECONDS", 0.001)

    with pytest.raises(images.ImageNormalizationError):
        await images.normalize_image(original, "image/jpeg")

    assert (tmp_path / digest[:2] / digest).read_bytes() == original


@pytest.mark.asyncio
async def test_oversized_pixels_rejected(monkeypatch):
    from app.config import settings
    from app.documents.images import ImageNormalizationError, normalize_image

    monkeypatch.setattr(settings, "DOCUMENT_MAX_IMAGE_PIXELS", 3)
    with pytest.raises(ImageNormalizationError):
        await normalize_image(jpeg_with_orientation_and_gps(), "image/jpeg")
