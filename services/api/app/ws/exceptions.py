"""Exception types shared by the generic WebSocket machinery."""


class WebSocketError(Exception):
    """Base class for every WebSocket infrastructure error."""

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
