"""Optional browser-rendered extraction fallback using Playwright."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE: bool | None = None


def is_browser_available() -> bool:
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is None:
        try:
            from playwright.async_api import async_playwright  # noqa: F401

            _PLAYWRIGHT_AVAILABLE = True
        except ImportError:
            _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


async def fetch_rendered_html(url: str, *, timeout_ms: int = 30000) -> str | None:
    """Render a page in a headless browser and return its HTML.

    Returns None if Playwright is not installed or rendering fails.
    """
    if not is_browser_available():
        logger.debug("Playwright not installed; browser fallback unavailable")
        return None

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                html = await page.content()
                return html
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning("Browser rendering failed for %s: %s", url, exc)
        return None
