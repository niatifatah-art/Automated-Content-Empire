class ACEError(Exception):
    """Base exception for user-facing ACE errors."""


class ConfigurationError(ACEError):
    """Raised when ACE configuration is invalid."""


class CatalogError(ACEError):
    """Raised when a platform or content type is unknown."""


class ProviderError(ACEError):
    """Base exception for model-provider failures."""


class ProviderUnavailable(ProviderError):
    """Raised when a provider cannot be used in the current environment."""


class ProviderRequestError(ProviderError):
    """Raised when a provider rejects or fails a request."""


class AllProvidersFailed(ProviderError):
    """Raised after every configured model target has failed."""

    def __init__(self, task: str, attempts: list[str]):
        self.task = task
        self.attempts = attempts
        details = "\n".join(f"  - {attempt}" for attempt in attempts)
        message = f"No model could complete task '{task}'."
        if details:
            message += f"\nAttempts:\n{details}"
        super().__init__(message)
