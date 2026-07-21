import logging
from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .exceptions import ScrapeError
from .validator import validate_public_url

logger = logging.getLogger(__name__)


def _configure_page(page: Page) -> None:
    def route_handler(route):
        if route.request.resource_type in {"image", "font", "media"}:
            route.abort()
        else:
            route.continue_()

    page.route("**/*", route_handler)
    page.set_default_navigation_timeout(30_000)
    page.set_default_timeout(10_000)


def fetch_rendered_html(url: str) -> str:
    validate_public_url(url)

    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
        )
        page = context.new_page()
        _configure_page(page)

        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            if response is not None and response.status >= 400:
                raise ScrapeError(f"Target returned HTTP {response.status}")

            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                logger.info("Network idle timeout; using rendered DOM")

            return page.content()

        except PlaywrightTimeoutError as exc:
            raise ScrapeError("Timed out loading target page") from exc

        finally:
            context.close()
            browser.close()
