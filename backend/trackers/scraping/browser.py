import logging
import os
from playwright.sync_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .exceptions import ScrapeError, UnsafeTargetUrlError
from .validator import validate_public_url

logger = logging.getLogger(__name__)


def _configure_page(page: Page) -> None:
    def secure_route(route):
        request = route.request

        if request.resource_type in {"image", "font", "media"}:
            route.abort()
            return

        try:
            validate_public_url(request.url)
        except UnsafeTargetUrlError as exc:
            logger.warning(f"Aborted unsafe subrequest/navigation to {request.url}: {exc}")
            route.abort("blockedbyclient")
            return

        route.continue_()

    page.route("**/*", secure_route)
    page.set_default_navigation_timeout(30_000)
    page.set_default_timeout(10_000)


def fetch_rendered_html(url: str) -> str:
    validate_public_url(url)

    with sync_playwright() as playwright:
        executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None
        browser: Browser = playwright.chromium.launch(
            headless=True,
            executable_path=executable_path,
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

            if response is not None:
                # Walk the redirect chain and validate every URL
                curr_request = response.request
                while curr_request:
                    validate_public_url(curr_request.url)
                    curr_request = curr_request.redirected_from

                validate_public_url(page.url)

                if response.status >= 400:
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
