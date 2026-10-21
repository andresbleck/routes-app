class UpstreamError(Exception):
    """A third-party provider failed or returned an unexpected response."""

    def __init__(self, provider: str, status_code: int | None = None):
        detail = f" with status {status_code}" if status_code else ""
        super().__init__(f"{provider} request failed{detail}")
        self.provider = provider
        self.status_code = status_code


class NoRouteFound(Exception):
    """The routing provider could not find a truck route between the points."""
