import struct
from io import BytesIO

import pytest
from PIL import Image

from app.documents import service
from app.documents.validation_process import detect_document_mime_type
from app.identity.models import User
from test_documents.fixtures import apple_gainmap_jpeg_bytes


def test_apple_gainmap_jpeg_is_recognized_as_jpeg():
    content = apple_gainmap_jpeg_bytes()
    with Image.open(BytesIO(content)) as image:
        assert image.format == "MPO" and image.n_frames == 2
    assert detect_document_mime_type(content) == "image/jpeg"


@pytest.mark.asyncio
async def test_gainmap_jpeg_passes_bounded_validator_and_mime_mismatch_stays_rejected():
    from app.documents.validation import UnsupportedDocumentFormatError, validate_document_content

    content = apple_gainmap_jpeg_bytes()
    assert await validate_document_content(content, "image/jpeg") == "image/jpeg"
    assert await validate_document_content(content, "application/octet-stream") == "image/jpeg"
    with pytest.raises(UnsupportedDocumentFormatError) as error:
        await validate_document_content(content, "image/heif")
    assert error.value.code == "document_mime_mismatch"


@pytest.mark.parametrize(
    "change",
    [
        {"role": "stereo"},
        {"version": "unknown"},
        {"version": "6553&#54;"},
        {"extra_frame": True},
        {"auxiliary_size": (33, 24)},
        {"xmp": b"not-xml"},
        {"xmp": b"<!DOCTYPE x [<!ENTITY e 'unsafe'>]><x>&e;</x>"},
        {"corrupt_auxiliary": True},
        {"primary_trailing": True},
        {"auxiliary_trailing": True},
    ],
)
def test_unsupported_or_invalid_multi_image_jpeg_stays_rejected(change):
    assert detect_document_mime_type(apple_gainmap_jpeg_bytes(**change)) is None


@pytest.mark.parametrize(
    "mutation", ["offset", "size", "type", "dependency", "truncated", "trailing"]
)
def test_malformed_or_non_gainmap_mpf_index_stays_rejected(mutation):
    data = bytearray(apple_gainmap_jpeg_bytes())
    entry = data.index(b"MPF\0") + 4 + 50
    if mutation == "offset":
        struct.pack_into("<I", data, entry + 16 + 8, 1)
    elif mutation == "size":
        struct.pack_into("<I", data, entry + 16 + 4, len(data) * 2)
    elif mutation == "type":
        struct.pack_into("<I", data, entry + 16, 0x020002)
    elif mutation == "dependency":
        struct.pack_into("<H", data, entry + 16 + 12, 1)
    elif mutation == "truncated":
        data = data[:-2]
    else:
        data.extend(b"unindexed-trailing-data\xff\xd9")
    assert detect_document_mime_type(bytes(data)) is None


def test_primary_pixel_limit_is_not_relaxed_for_gainmap_jpeg():
    assert detect_document_mime_type(apple_gainmap_jpeg_bytes(), max_pixels=767) is None


@pytest.mark.asyncio
async def test_gainmap_derivative_uses_primary_orientation_and_strips_auxiliary_metadata():
    from app.documents.images import normalize_image

    original = apple_gainmap_jpeg_bytes()
    derivative = await normalize_image(original, "image/jpeg")
    assert b"HDRGainMap" not in derivative and b"MPF\0" not in derivative
    with Image.open(BytesIO(derivative)) as image:
        assert image.format == "JPEG" and getattr(image, "n_frames", 1) == 1
        assert image.size == (24, 32)  # Primary32x24 with orientation6, not auxiliary16x12.
        red, green, blue = image.getpixel((12, 16))
        assert red > 200 and green < 30 and blue < 30
        assert not image.getexif() and "xmp" not in image.info


@pytest.mark.asyncio
@pytest.mark.integration
async def test_accepted_gainmap_upload_preserves_original(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(
        email="gainmap-synthetic@example.test", password_hash="synthetic", display_name="Synthetic"
    )
    db_session.add(user)
    await db_session.commit()
    content = apple_gainmap_jpeg_bytes()
    result = await service.upload_document(
        db_session, user.id, content, "synthetic.jpg", "image/jpeg"
    )
    assert result.mime_type == "image/jpeg"
    assert (tmp_path / result.storage_path).read_bytes() == content
