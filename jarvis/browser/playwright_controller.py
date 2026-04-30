"""
Jarvis v2.0 — Playwright Browser Controller
=============================================
Level 2+3 browser intelligence. NOT a blind robot clicking pixels —
this works via the DOM, like a real browser automation engine.

Capabilities:
  - Launch & manage browser instances (Chromium/Brave)
  - Navigate, search, open/close tabs
  - Read page content (full DOM, not just visible text)
  - Click elements by selector, text, or AI-determined target
  - Extract structured data from pages
  - Execute arbitrary JavaScript
  - Screenshot capture for vision analysis
  - Multi-tab orchestration
  - Form filling, login flows
  - Download management
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.browser")


@dataclass
class TabInfo:
    """Information about an open browser tab."""
    id: int
    url: str
    title: str
    is_active: bool = False
    domain: str = ""

    def __post_init__(self):
        if self.url and not self.domain:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            self.domain = parsed.netloc


@dataclass
class PageContent:
    """Extracted content from a web page."""
    url: str
    title: str
    text: str
    html: str = ""
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class PlaywrightController:
    """
    Core browser automation engine powered by Playwright.
    Connects to existing browser or launches a new one.

    This is the muscle. The BrowserAgent is the brain.
    """

    def __init__(self, browser_path: str = None, headless: bool = False):
        """
        Args:
            browser_path: Path to browser executable (e.g., Brave).
                          None = use default Chromium.
            headless: Run without visible window (for scraping).
        """
        self._browser_path = browser_path or self._find_brave()
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: dict[int, object] = {}  # page_id -> Page
        self._active_page_id: int = 0
        self._page_counter: int = 0
        self._launched = False

    @staticmethod
    def _find_brave() -> Optional[str]:
        """Auto-detect Brave browser path on Windows."""
        possible_paths = [
            Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
            Path(r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
            Path.home() / r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
        for p in possible_paths:
            if p.exists():
                logger.info(f"Found Brave at: {p}")
                return str(p)
        return None  # Fall back to Playwright's bundled Chromium

    async def launch(self):
        """Launch browser instance."""
        if self._launched:
            return

        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            launch_kwargs = {
                "headless": self._headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }

            if self._browser_path:
                launch_kwargs["executable_path"] = self._browser_path

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
            )

            # --- Native Ad-Blocker (Network Interception) ---
            async def intercept_route(route):
                url = route.request.url.lower()
                ad_keywords = [
                    "googlesyndication.com", "adservice.google", "doubleclick.net",
                    "googleadservices.com", "youtube.com/api/stats/ads", "youtube.com/pagead/",
                    "pagead2", "adsystem", "analytics.js", "tracking", "tracker",
                    "popunder", "popads", "onclickads"
                ]
                if any(str(bad) in url for bad in ad_keywords):
                    await route.abort()
                else:
                    await route.continue_()

            await self._context.route("**/*", intercept_route)

            # Open initial tab
            page = await self._context.new_page()
            self._page_counter += 1
            self._pages[self._page_counter] = page
            self._active_page_id = self._page_counter
            self._launched = True

            logger.info("Browser launched successfully")

        except Exception as e:
            logger.error(f"Browser launch failed: {e}")
            raise

    async def shutdown(self):
        """Clean shutdown of browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._launched = False
        self._pages.clear()
        logger.info("Browser shut down")

    @property
    def active_page(self):
        """Get the currently active page."""
        return self._pages.get(self._active_page_id)

    @property
    def is_launched(self) -> bool:
        return self._launched

    # ── Navigation ──────────────────────────────────────────────

    async def navigate(self, url: str, wait_for: str = "domcontentloaded") -> bool:
        """
        Navigate to a URL in the active tab.
        
        Args:
            url: URL to navigate to
            wait_for: Event to wait for ('domcontentloaded', 'load', 'networkidle')
        """
        await self._ensure_launched()
        page = self.active_page
        if not page:
            return False

        try:
            # Add https:// if missing
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            await page.goto(url, wait_until=wait_for, timeout=30000)
            logger.info(f"Navigated to: {url}")
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    async def go_back(self) -> bool:
        """Navigate back in history."""
        page = self.active_page
        if page:
            await page.go_back()
            return True
        return False

    async def go_forward(self) -> bool:
        """Navigate forward in history."""
        page = self.active_page
        if page:
            await page.go_forward()
            return True
        return False

    async def reload(self) -> bool:
        """Reload the current page."""
        page = self.active_page
        if page:
            await page.reload()
            return True
        return False

    # ── Tab Management ──────────────────────────────────────────

    async def new_tab(self, url: str = None) -> int:
        """Open a new tab, optionally navigating to a URL."""
        await self._ensure_launched()
        page = await self._context.new_page()
        self._page_counter += 1
        tab_id = self._page_counter
        self._pages[tab_id] = page
        self._active_page_id = tab_id

        if url:
            await self.navigate(url)

        logger.info(f"New tab #{tab_id} opened" + (f" → {url}" if url else ""))
        return tab_id

    async def close_tab(self, tab_id: int = None) -> bool:
        """Close a tab by ID, or the active tab."""
        tid = tab_id or self._active_page_id
        page = self._pages.get(tid)
        if not page:
            return False

        await page.close()
        del self._pages[tid]

        # Switch to another tab
        if self._pages:
            self._active_page_id = max(self._pages.keys())
        else:
            self._active_page_id = 0

        logger.info(f"Tab #{tid} closed")
        return True

    async def close_all_tabs(self):
        """Close all tabs except one (browser needs at least one)."""
        tab_ids = list(self._pages.keys())
        for tid in tab_ids[:-1]:  # Keep the last one
            await self.close_tab(tid)
        if tab_ids:
            # Navigate the remaining tab to blank
            page = self.active_page
            if page:
                await page.goto("about:blank")
        logger.info("All tabs closed")

    async def switch_tab(self, tab_id: int) -> bool:
        """Switch to a specific tab."""
        if tab_id in self._pages:
            self._active_page_id = tab_id
            page = self._pages[tab_id]
            await page.bring_to_front()
            logger.info(f"Switched to tab #{tab_id}")
            return True
        return False

    async def get_all_tabs(self) -> list[TabInfo]:
        """Get info about all open tabs."""
        tabs = []
        for tid, page in self._pages.items():
            try:
                tabs.append(TabInfo(
                    id=tid,
                    url=page.url,
                    title=await page.title(),
                    is_active=(tid == self._active_page_id),
                ))
            except Exception:
                tabs.append(TabInfo(id=tid, url="unknown", title="unknown"))
        return tabs

    # ── Search ──────────────────────────────────────────────────

    async def search_google(self, query: str) -> bool:
        """Search Google."""
        return await self.navigate(f"https://www.google.com/search?q={query.replace(' ', '+')}")

    async def search_youtube(self, query: str) -> bool:
        """Search YouTube."""
        return await self.navigate(
            f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        )

    async def search_duckduckgo(self, query: str) -> bool:
        """Search DuckDuckGo (privacy-friendly)."""
        return await self.navigate(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")

    async def search_site(self, site: str, query: str) -> bool:
        """Search within a specific site via Google."""
        full = f"site:{site} {query}"
        return await self.search_google(full)

    # ── Content Extraction ──────────────────────────────────────

    async def get_page_content(self, include_html: bool = False) -> Optional[PageContent]:
        """
        Extract meaningful content from the current page.
        Uses JavaScript to get clean text, links, and metadata.
        """
        page = self.active_page
        if not page:
            return None

        try:
            # Extract content via JS
            data = await page.evaluate("""() => {
                // Get clean text content
                const getTextContent = () => {
                    const clone = document.body.cloneNode(true);
                    // Remove scripts, styles, nav, footer
                    const removeSelectors = ['script', 'style', 'nav', 'footer', 
                                             'header', '.sidebar', '.ad', '.advertisement',
                                             '[role="navigation"]', '[role="banner"]'];
                    removeSelectors.forEach(sel => {
                        clone.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return clone.innerText.replace(/\\n{3,}/g, '\\n\\n').trim();
                };

                // Get all links
                const getLinks = () => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({ text: a.innerText.trim(), href: a.href }))
                        .filter(l => l.text && l.href.startsWith('http'))
                        .slice(0, 50);  // Limit to 50 links
                };

                // Get images
                const getImages = () => {
                    return Array.from(document.querySelectorAll('img[src]'))
                        .map(img => ({ alt: img.alt || '', src: img.src }))
                        .filter(i => i.src.startsWith('http'))
                        .slice(0, 20);
                };

                // Get metadata
                const getMeta = () => {
                    const meta = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        if (key) meta[key] = m.getAttribute('content') || '';
                    });
                    return meta;
                };

                return {
                    title: document.title,
                    url: window.location.href,
                    text: getTextContent(),
                    links: getLinks(),
                    images: getImages(),
                    metadata: getMeta(),
                };
            }""")

            content = PageContent(
                url=data["url"],
                title=data["title"],
                text=data["text"][:15000],  # Cap at 15k chars for LLM context
                links=data.get("links", []),
                images=data.get("images", []),
                metadata=data.get("metadata", {}),
            )

            if include_html:
                content.html = await page.content()

            logger.info(f"Extracted {len(content.text)} chars from {content.url}")
            return content

        except Exception as e:
            logger.error(f"Content extraction failed: {e}")
            return None

    async def get_page_text(self) -> str:
        """Get just the text content of the current page."""
        content = await self.get_page_content()
        return content.text if content else ""

    async def get_current_url(self) -> str:
        """Get the URL of the active tab."""
        page = self.active_page
        return page.url if page else ""

    async def get_current_title(self) -> str:
        """Get the title of the active tab."""
        page = self.active_page
        return await page.title() if page else ""

    # ── Interaction ─────────────────────────────────────────────

    async def click(self, selector: str, timeout: int = 5000) -> bool:
        """Click an element by CSS selector."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.click(selector, timeout=timeout)
            logger.info(f"Clicked: {selector}")
            return True
        except Exception as e:
            logger.error(f"Click failed on '{selector}': {e}")
            return False

    async def click_text(self, text: str, exact: bool = False) -> bool:
        """Click an element containing specific text."""
        page = self.active_page
        if not page:
            return False
        try:
            locator = page.get_by_text(text, exact=exact)
            await locator.first.click(timeout=5000)
            logger.info(f"Clicked text: '{text}'")
            return True
        except Exception as e:
            logger.error(f"Click text failed for '{text}': {e}")
            return False

    async def click_link(self, text: str) -> bool:
        """Click a link by its text."""
        page = self.active_page
        if not page:
            return False
        try:
            locator = page.get_by_role("link", name=text)
            await locator.first.click(timeout=5000)
            return True
        except Exception as e:
            logger.error(f"Click link failed for '{text}': {e}")
            return False

    async def click_button(self, text: str) -> bool:
        """Click a button by its text."""
        page = self.active_page
        if not page:
            return False
        try:
            locator = page.get_by_role("button", name=text)
            await locator.first.click(timeout=5000)
            return True
        except Exception as e:
            logger.error(f"Click button failed for '{text}': {e}")
            return False

    async def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        """Type text into an input field."""
        page = self.active_page
        if not page:
            return False
        try:
            if clear_first:
                await page.fill(selector, text)
            else:
                await page.type(selector, text)
            logger.info(f"Typed into '{selector}': {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Type failed on '{selector}': {e}")
            return False

    async def type_and_enter(self, selector: str, text: str) -> bool:
        """Type text and press Enter (for search bars)."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.fill(selector, text)
            await page.press(selector, "Enter")
            return True
        except Exception as e:
            logger.error(f"Type+Enter failed: {e}")
            return False

    async def press_key(self, key: str) -> bool:
        """Press a keyboard key (e.g., 'Enter', 'Escape', 'Tab')."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.keyboard.press(key)
            return True
        except Exception as e:
            logger.error(f"Key press failed: {e}")
            return False

    async def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        """Scroll the page."""
        page = self.active_page
        if not page:
            return False
        try:
            delta = amount if direction == "down" else -amount
            await page.mouse.wheel(0, delta)
            return True
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False

    async def scroll_to_bottom(self) -> bool:
        """Scroll to the bottom of the page."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return True
        except Exception:
            return False

    async def scroll_to_top(self) -> bool:
        """Scroll to the top of the page."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.evaluate("window.scrollTo(0, 0)")
            return True
        except Exception:
            return False

    # ── JavaScript Execution ────────────────────────────────────

    async def execute_js(self, script: str) -> any:
        """Execute JavaScript on the current page and return the result."""
        page = self.active_page
        if not page:
            return None
        try:
            result = await page.evaluate(script)
            return result
        except Exception as e:
            logger.error(f"JS execution failed: {e}")
            return None

    async def inject_css(self, css: str) -> bool:
        """Inject CSS into the current page."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.add_style_tag(content=css)
            return True
        except Exception:
            return False

    # ── Screenshots ─────────────────────────────────────────────

    async def screenshot(self, path: str = None, full_page: bool = False) -> Optional[bytes]:
        """
        Take a screenshot of the current page.
        Returns raw PNG bytes (for vision analysis) or saves to file.
        """
        page = self.active_page
        if not page:
            return None
        try:
            kwargs = {"full_page": full_page, "type": "png"}
            if path:
                kwargs["path"] = path

            data = await page.screenshot(**kwargs)
            logger.info(f"Screenshot captured ({len(data)} bytes)")
            return data
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None

    async def screenshot_element(self, selector: str) -> Optional[bytes]:
        """Take a screenshot of a specific element."""
        page = self.active_page
        if not page:
            return None
        try:
            element = page.locator(selector)
            data = await element.screenshot(type="png")
            return data
        except Exception as e:
            logger.error(f"Element screenshot failed: {e}")
            return None

    # ── Waiting ─────────────────────────────────────────────────

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for an element to appear on the page."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        """Wait for page navigation to complete."""
        page = self.active_page
        if not page:
            return False
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_seconds(self, seconds: float):
        """Simple wait (for page animations, dynamic loading, etc.)."""
        await asyncio.sleep(seconds)

    # ── Smart Actions (Site-Specific) ───────────────────────────

    async def youtube_play(self, query: str) -> bool:
        """Search and play a video on YouTube."""
        await self.navigate("https://www.youtube.com")
        await self.wait_seconds(1.5)

        # Type in search
        try:
            page = self.active_page
            search_input = page.locator('input#search, input[name="search_query"]')
            await search_input.fill(query)
            await search_input.press("Enter")
            await self.wait_seconds(2)

            # Click first video result
            first_video = page.locator("ytd-video-renderer a#video-title").first
            await first_video.click()
            await self.wait_seconds(2)

            logger.info(f"Playing YouTube: {query}")
            return True
        except Exception as e:
            logger.error(f"YouTube play failed: {e}")
            return False

    async def youtube_pause(self) -> bool:
        """Pause/play the current YouTube video."""
        return await self.press_key("k")  # YouTube shortcut

    async def youtube_fullscreen(self) -> bool:
        """Toggle fullscreen on YouTube."""
        return await self.press_key("f")

    async def youtube_volume(self, direction: str = "up") -> bool:
        """Adjust YouTube volume."""
        key = "ArrowUp" if direction == "up" else "ArrowDown"
        for _ in range(5):  # 5 steps
            await self.press_key(key)
        return True

    # ── Utility ─────────────────────────────────────────────────

    async def _ensure_launched(self):
        """Make sure browser is running."""
        if not self._launched:
            await self.launch()

    async def get_context_summary(self) -> dict:
        """
        Get a summary of the current browser state.
        Used by BrowserAgent for context-aware decisions.
        """
        tabs = await self.get_all_tabs()
        active_url = await self.get_current_url()
        active_title = await self.get_current_title()

        return {
            "launched": self._launched,
            "tab_count": len(tabs),
            "active_tab": {
                "id": self._active_page_id,
                "url": active_url,
                "title": active_title,
            },
            "all_tabs": [
                {"id": t.id, "title": t.title, "domain": t.domain}
                for t in tabs
            ],
        }
