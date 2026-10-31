from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image


def jpeg_with_orientation_and_gps() -> bytes:
    image = Image.new("RGB", (2, 4), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[34853] = {1: "N", 2: (52.0, 0.0, 0.0), 3: "E", 4: (21.0, 0.0, 0.0)}
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


@pytest.mark.asyncio
async def test_orientation_without_gps():
    from app.documents.images import normalize_image

    original = jpeg_with_orientation_and_gps()
    with Image.open(BytesIO(original)) as image:
        assert image.getexif().get_ifd(34853)[1] == "N"

    result = await normalize_image(original, "image/jpeg")

    assert result.startswith(b"\xff\xd8")
    with Image.open(BytesIO(result)) as image:
        assert image.size == (4, 2)
        assert image.getexif().get_ifd(34853) == {}


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


ORIENTATION_SIZES = {1: (20, 40), 3: (20, 40), 6: (40, 20), 8: (40, 20)}
TOP_LEFT_COLORS = {1: "red", 3: "black", 6: "blue", 8: "green"}


def synthetic_corners(*, orientation: int = 1, image_format: str = "JPEG") -> bytes:
    image = Image.new("RGB", (20, 40), "white")
    # Deliberately asymmetric corners and narrow dark strokes, not receipt content.
    image.paste((255, 0, 0), (0, 0, 5, 5))
    image.paste((0, 255, 0), (15, 0, 20, 5))
    image.paste((0, 0, 255), (0, 35, 5, 40))
    image.paste((0, 0, 0), (15, 35, 20, 40))
    image.paste((0, 0, 0), (8, 10, 12, 30))
    exif = Image.Exif()
    exif[274] = orientation
    exif[34853] = {1: "N", 2: (52.0, 0.0, 0.0), 3: "E", 4: (21.0, 0.0, 0.0)}
    output = BytesIO()
    if image_format == "JPEG":
        image.save(output, format=image_format, exif=exif)
        # Synthetic XMP APP1 payload which must not reach the derivative.
        return (
            output.getvalue()[:2]
            + b"\xff\xe1\x00;http://ns.adobe.com/xap/1.0/\x00synthetic-xmp"
            + output.getvalue()[2:]
        )
    image.save(output, format=image_format)
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
async def test_normalize_image_applies_exif_orientation_and_strips_metadata(orientation):
    from app.documents.images import normalize_image

    original = synthetic_corners(orientation=orientation)
    original_hash = sha256(original).hexdigest()

    result = await normalize_image(original, "image/jpeg")

    assert sha256(original).hexdigest() == original_hash
    assert result.startswith(b"\xff\xd8")
    assert b"http://ns.adobe.com" not in result
    with Image.open(BytesIO(result)) as image:
        assert image.mode == "RGB"
        assert image.size == ORIENTATION_SIZES[orientation]
        red, green, blue = image.getpixel((2, 2))
        if TOP_LEFT_COLORS[orientation] == "red":
            assert red > green and red > blue
        elif TOP_LEFT_COLORS[orientation] == "green":
            assert green > red and green > blue
        elif TOP_LEFT_COLORS[orientation] == "blue":
            assert blue > red and blue > green
        else:
            assert max(red, green, blue) < 30
        assert not image.getexif()
        assert "icc_profile" not in image.info


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime", "image_format"),
    [("image/jpeg", "JPEG"), ("image/png", "PNG"), ("image/heif", "HEIF")],
)
async def test_normalize_image_formats_share_bounded_jpeg_path(mime, image_format):
    from app.documents.images import normalize_image

    if image_format == "HEIF":
        pytest.importorskip("pillow_heif")
        from test_documents.fixtures import valid_heic_bytes

        original = valid_heic_bytes()
    else:
        original = synthetic_corners(image_format=image_format)

    result = await normalize_image(original, mime, max_edge=2, max_output_bytes=10_000)

    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert max(image.size) <= 2
        assert not image.getexif()


@pytest.mark.asyncio
async def test_normalize_image_honors_explicit_edge_and_output_bounds():
    from app.documents.images import ImageNormalizationError, normalize_image

    original = synthetic_corners()
    result = await normalize_image(original, "image/jpeg", max_edge=1, max_output_bytes=10_000)
    with Image.open(BytesIO(result)) as image:
        assert image.size == (1, 1)

    with pytest.raises(ImageNormalizationError):
        await normalize_image(original, "image/jpeg", max_output_bytes=10)
