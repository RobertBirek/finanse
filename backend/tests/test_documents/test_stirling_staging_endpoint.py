"""Exercise staging endpoint wiring without starting Docker or using real HTTP."""

import ast
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["192.0.2.23", "198.51.100.42"])
async def test_staging_conversion_uses_its_private_endpoint(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    from app import worker
    from app.documents import ocr_pipeline

    # Execute only the real staging test's patch: never its Docker/startup code.
    source = Path(__file__).resolve().parents[1] / "test_stirling_staging.py"
    tree = ast.parse(source.read_text())
    statements: list[ast.stmt] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "setattr"
        and len(node.value.args) >= 2
        and isinstance(node.value.args[1], ast.Constant)
        and node.value.args[1].value == "STIRLING_IMG_TO_PDF_URL"
    ]
    assert len(statements) == 1, "Expected one staging conversion endpoint patch"
    monkeypatch.setattr(ocr_pipeline, "STIRLING_IMG_TO_PDF_URL", "http://wrong-endpoint.invalid")
    exec(  # noqa: S102 - one selected statement from our trusted staging test, not user input
        compile(ast.Module(body=statements, type_ignores=[]), str(source), "exec"),
        {
            "worker": worker,
            "ocr_pipeline": ocr_pipeline,
            "monkeypatch": monkeypatch,
            "address": address,
        },
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"%PDF-synthetic-response")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        result = await worker._convert_image_to_pdf(client, "synthetic.png", b"synthetic-image")
    assert len(requests) == 1
    assert str(requests[0].url) == f"http://{address}:8080/api/v1/convert/img/pdf"
    assert requests[0].method == "POST"
    assert result == b"%PDF-synthetic-response"
