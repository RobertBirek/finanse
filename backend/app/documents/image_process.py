"""Image derivative worker run outside the application process."""

import json
import resource
import sys
import warnings
from io import BytesIO


def normalize_image(
    content: bytes, mime: str, *, thumbnail: bool, max_pixels: int, max_edge: int, quality: int
) -> bytes:
    from PIL import Image, ImageOps

    if mime == "image/heif":
        from pillow_heif import open_heif, register_heif_opener

        register_heif_opener(thumbnails=False)
        heif = open_heif(content)
        if heif.primary_index is None or not 0 <= heif.primary_index < len(heif):
            raise ValueError("HEIF has no primary image")
        image = heif[heif.primary_index].to_pillow()
    else:
        image = Image.open(BytesIO(content))

    with image, warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        if image.width * image.height > max_pixels:
            raise ValueError("Image exceeds pixel limit")
        image = ImageOps.exif_transpose(image)
        if thumbnail:
            image.thumbnail((max_edge, max_edge))
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, "white")
            rgba = image.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()


def main() -> None:
    limits = json.loads(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory"], limits["memory"]))
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    content = sys.stdin.buffer.read(limits["bytes"] + 1)
    if len(content) > limits["bytes"]:
        raise ValueError("Image exceeds file limit")
    output = normalize_image(
        content,
        limits["mime"],
        thumbnail=limits["thumbnail"],
        max_pixels=limits["pixels"],
        max_edge=limits["edge"],
        quality=limits["quality"],
    )
    if len(output) > limits["output_bytes"]:
        raise ValueError("Image derivative exceeds output limit")
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
