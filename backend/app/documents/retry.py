import httpx

from app.config import settings


def is_retryable_ocr_error(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {
        408,
        429,
        500,
        502,
        503,
        504,
    }


def retry_delay_seconds(attempt_count: int) -> int:
    return settings.DOCUMENT_RETRY_DELAYS_SECONDS[attempt_count - 1]
