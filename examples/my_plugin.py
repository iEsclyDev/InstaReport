"""Example external plugin — drop this file into your configured plugin directory."""
from typing import Any, Callable
from instareport.plugins.base import PlatformPlugin


class ExampleXPlugin(PlatformPlugin):
    """Example plugin that adds a custom platform."""

    @property
    def platform_key(self) -> str:
        return "example_x"

    @property
    def display_name(self) -> str:
        return "Example Platform X"

    @property
    def description(self) -> str:
        return "An example external plugin — copy and modify for your own platform"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def login(self, page: Any, user: str, pw: str,
                    log_fn: Callable[..., Any]) -> bool:
        log_fn(f"  [X] Logging in {user}...")
        await page.goto("https://example.com/login")
        # Add your login logic here
        return True

    async def report(self, page: Any, user: str, pw: str,
                     target: str, reason: str,
                     log_fn: Callable[..., Any]) -> bool:
        log_fn(f"  [X] Reporting {target} for {reason}...")
        await page.goto("https://example.com/report")
        # Add your report logic here
        return True
