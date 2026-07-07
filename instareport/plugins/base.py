"""PlatformPlugin ABC — interface that all report plugins must implement."""
from abc import ABC, abstractmethod
from typing import Any, Callable


class PlatformPlugin(ABC):
    """Base class for platform-specific report plugins."""

    def __init__(self) -> None:
        self._enabled: bool = True
        self._source: str = "builtin"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    @abstractmethod
    def platform_key(self) -> str:
        ...

    @property
    def display_name(self) -> str:
        return self.platform_key.replace("_", " ").title()

    @property
    def description(self) -> str:
        return ""

    @property
    def version(self) -> str:
        return "1.0.0"

    @abstractmethod
    async def login(self, page: Any, user: str, pw: str, log_fn: Callable[..., Any]) -> bool:
        ...

    @abstractmethod
    async def report(self, page: Any, user: str, pw: str, target: str, reason: str,
                     log_fn: Callable[..., Any]) -> bool:
        ...
