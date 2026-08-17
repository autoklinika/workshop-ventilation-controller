"""Touch-friendly web client for the workshop ventilation controller."""

from .app import ApiResponse, WebApplication
from .client import CoreClientError, CoreUnixClient
from .config import WebUiConfig

__all__ = ["ApiResponse", "CoreClientError", "CoreUnixClient", "WebApplication", "WebUiConfig"]
