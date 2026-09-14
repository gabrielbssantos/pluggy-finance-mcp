from typing import Literal

Code = Literal[
    "INVALID_ARGUMENT",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "RATE_LIMITED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_ERROR",
    "CONFIGURATION_ERROR",
]


class FinanceError(Exception):
    def __init__(self, code: Code, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def upstream_error(status: int) -> FinanceError:
    codes: dict[int, Code] = {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        502: "UPSTREAM_UNAVAILABLE",
        503: "UPSTREAM_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }
    return FinanceError(codes.get(status, "UPSTREAM_ERROR"), status in {429, 502, 503, 504})
