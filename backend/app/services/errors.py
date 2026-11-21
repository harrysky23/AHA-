class LearningError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, fallback: bool = True, retry_after: int | None = None):
        self.code, self.message, self.status, self.fallback = code, message, status, fallback
        self.retry_after = retry_after
        # Optional diagnostics for the explicit synthetic live-check CLI only.
        # These are never serialized by the HTTP exception handler or logged by the app.
        self.upstream_status = None
        self.upstream_message = None
        super().__init__(message)
