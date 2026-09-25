import logging
from typing import Optional, Dict, Any
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

import config

logger = logging.getLogger("BrowserManager")


class BrowserManager:
    """
    Manages Playwright Chromium lifecycle, browser context configuration,
    and anti-detection settings for job scraping tasks.
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        slow_mo: Optional[int] = None,
        proxy: Optional[Dict[str, str]] = None,
    ):
        self.headless = headless if headless is not None else config.DEFAULT_HEADLESS
        self.slow_mo = slow_mo if slow_mo is not None else config.SLOW_MO_MS
        self.proxy = proxy
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    def start(self) -> "BrowserManager":
        """Starts Playwright and launches the Chromium browser instance."""
        if not self.playwright:
            logger.info("Initializing Playwright...")
            self.playwright = sync_playwright().start()

        if not self.browser:
            logger.info(
                f"Launching Playwright Chromium (headless={self.headless}, slow_mo={self.slow_mo}ms)..."
            )
            # Anti-detection & performance flags tailored for Chromium
            chromium_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080",
                "--start-maximized",
            ]

            launch_kwargs: Dict[str, Any] = {
                "headless": self.headless,
                "args": chromium_args,
                "slow_mo": self.slow_mo,
            }

            if self.proxy:
                launch_kwargs["proxy"] = self.proxy

            if config.CHROME_CHANNEL:
                launch_kwargs["channel"] = config.CHROME_CHANNEL

            # Launch Playwright Chromium explicitly
            self.browser = self.playwright.chromium.launch(**launch_kwargs)
            logger.info("Chromium launched successfully.")

        return self

    def new_context(self, **kwargs) -> BrowserContext:
        """
        Creates a new isolated browser context with anti-bot evasion scripts
        and realistic browser headers.
        """
        if not self.browser:
            self.start()

        context_options: Dict[str, Any] = {
            "viewport": config.VIEWPORT,
            "user_agent": config.USER_AGENT,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "ignore_https_errors": True,
        }
        context_options.update(kwargs)

        context = self.browser.new_context(**context_options)

        # Anti-bot detection script injection
        context.add_init_script("""
            // Hide webdriver flag
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // Overwrite languages and plugins to look authentic
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

        return context

    def get_page(self, context: Optional[BrowserContext] = None) -> Page:
        """
        Convenience method to retrieve a freshly configured page.
        If no context is provided, uses or creates a default context.
        """
        if context is None:
            if self.context is None:
                self.context = self.new_context()
            target_context = self.context
        else:
            target_context = context

        page = target_context.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT_MS)
        return page

    def close(self):
        """Clean up contexts, browser, and playwright instance."""
        try:
            if self.context:
                logger.debug("Closing default context...")
                self.context.close()
                self.context = None
            if self.browser:
                logger.info("Closing Chromium browser...")
                self.browser.close()
                self.browser = None
            if self.playwright:
                logger.info("Stopping Playwright...")
                self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.warning(f"Error during browser teardown: {e}")

    def __enter__(self) -> "BrowserManager":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
