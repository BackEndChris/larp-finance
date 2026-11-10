class HistoricalPriceError(ValueError):
    """A permanent, credential-safe historical-data failure."""


class TemporaryHistoricalPriceError(HistoricalPriceError):
    """A retryable failure with a bounded scheduling delay."""

    def __init__(self, message="Historical data temporarily unavailable", retry_after=300):
        super().__init__(message)
        self.retry_after = max(60, min(int(retry_after), 86400))
