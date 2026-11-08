"""Stable service error codes; details must never expose another owner's resources."""


class ImportError(ValueError):
    def __init__(self, code: str, detail: str, http_status: int = 409) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(detail)
