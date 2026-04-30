"""
Jarvis v2.0 — Browser Agent (The Brain Behind the Browser)
============================================================
The BrowserAgent doesn't just execute clicks — it THINKS about what to do.

Flow:
  User: "Search best GPUs, open top 3, compare them"
  → Agent breaks this into steps
  → Step 1: Search "best GPUs 2026" on Google
  → Step 2: Extract top 3 result URLs
  → Step 3: Open each in a new tab
  → Step 4: Extract content from all 3
  → Step 5: Send to LLM for comparison
  → Step 6: Present summary in HUD

This agent uses the LLM to:
  - Parse natural language into browser actions
  - Decide which selectors to use
  - Understand page context
  - Generate multi-step plans
"""

import asyncio
import logging
import json
from typing import Optional
from dataclasses import dataclass, field

from jarvis.browser.playwright_controller import PlaywrightController, PageContent

logger = logging.getLogger("jarvis.browser.agent")


@dataclass
class BrowserAction:
    """A single browser action in a multi-step plan."""
    step: int
    action: str  # navigate, search, click, extract, screenshot, etc.
    target: str  # URL, selector, query, etc.
    description: str
    completed: bool = False
    result: str = ""
    error: str = ""


@dataclass
class BrowserTask:
    """A multi-step browser task."""
    original_request: str
    steps: list[BrowserAction] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    result_summary: str = ""


class BrowserAgent:
    """
    Jarvis's browser intelligence layer.

    Sits between user commands and the Playwright controller.
    Uses the LLM to plan, execute, and adapt browser actions.
    """

    def __init__(self, brain, controller: PlaywrightController = None):
        """
        Args:
            brain: JarvisBrain instance (for LLM access)
            controller: PlaywrightController (created if not provided)
        """
        self.brain = brain
        self.controller = controller or PlaywrightController()
        self._current_task: Optional[BrowserTask] = None
        self._action_history: list[dict] = []

    async def execute(self, user_request: str) -> str:
        """
        Main entry point. Takes a natural language request,
        plans the browser actions, executes them, and returns results.

        This is what the Orchestrator calls.
        """
        logger.info(f"Browser agent received: {user_request}")

        # Ensure browser is running
        if not self.controller.is_launched:
            await self.controller.launch()

        # Get current browser context for the LLM
        context = await self.controller.get_context_summary()

        # Ask LLM to plan the actions
        plan = await self._plan_actions(user_request, context)
        if not plan:
            return "I couldn't figure out what to do in the browser. Could you be more specific?"

        # Execute the plan
        self._current_task = BrowserTask(
            original_request=user_request,
            steps=plan,
            status="running",
        )

        results = []
        for action in plan:
            try:
                result = await self._execute_action(action)
                action.completed = True
                action.result = result
                results.append(f"✓ Step {action.step}: {action.description} — {result}")
                logger.info(f"Step {action.step} completed: {action.description}")
            except Exception as e:
                action.error = str(e)
                results.append(f"✗ Step {action.step}: {action.description} — Failed: {e}")
                logger.error(f"Step {action.step} failed: {e}")

                # Ask LLM if we should continue or abort
                should_continue = await self._should_continue_after_error(
                    action, plan, str(e)
                )
                if not should_continue:
                    break

        self._current_task.status = "completed"

        # If the task involved content extraction, summarize with LLM
        extracted_content = [a.result for a in plan if a.action == "extract" and a.result]
        if extracted_content:
            summary = await self._summarize_results(user_request, extracted_content)
            self._current_task.result_summary = summary
            return summary

        # Return step-by-step results
        return "\n".join(results) if results else "Done."

    async def _plan_actions(self, request: str, context: dict) -> list[BrowserAction]:
        """
        Use LLM to plan browser actions from natural language.
        """
        plan_prompt = f"""You are a browser automation planner. Convert the user's request into a JSON list of browser actions.

CURRENT BROWSER STATE:
{json.dumps(context, indent=2)}

USER REQUEST: "{request}"

AVAILABLE ACTIONS:
- navigate: Go to a URL. Target = URL string.
- search_google: Search Google. Target = search query.
- search_youtube: Search YouTube. Target = search query.
- search_duckduckgo: Search DuckDuckGo. Target = search query.
- youtube_play: Search and play on YouTube. Target = search query.
- click_text: Click element by visible text. Target = text to click.
- click_button: Click a button by text. Target = button text.
- click_link: Click a link by text. Target = link text.
- type_text: Type into a field. Target = "selector|||text" format.
- type_and_enter: Type and press Enter. Target = "selector|||text" format.
- extract: Extract page content. Target = "full" or "text_only".
- screenshot: Take screenshot. Target = "page" or "fullpage".
- new_tab: Open a new tab. Target = optional URL.
- close_tab: Close current tab. Target = "current".
- close_all_tabs: Close all tabs. Target = "all".
- scroll: Scroll page. Target = "up" or "down".
- press_key: Press a key. Target = key name (Enter, Escape, etc.).
- wait: Wait for page load. Target = seconds as string.
- go_back: Go back. Target = "".
- youtube_pause: Pause/play YouTube. Target = "".
- youtube_fullscreen: Toggle YouTube fullscreen. Target = "".
- youtube_volume: Adjust YouTube volume. Target = "up" or "down".

IMPORTANT RULES: 
1. To search Google, YouTube, or DuckDuckGo, YOU MUST use `search_google`, `search_youtube`, or `search_duckduckgo` DIRECTLY. Do NOT use `new_tab` + `type_and_enter` on search engines (their DOM selectors change frequently and will break).
2. Plan smart! Combine steps efficiently. For YouTube searches, use `youtube_play` directly instead of searching and clicking.

Respond with ONLY a JSON array, no markdown. Each item:
{{"step": 1, "action": "action_name", "target": "target_value", "description": "human readable description"}}"""

        try:
            response = await self.brain.quick_think(
                plan_prompt,
                system_override="You are a precise JSON planner. Output ONLY valid JSON arrays. No markdown, no explanation."
            )

            # Parse JSON from response
            response = response.strip()
            # Handle potential markdown wrapping
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
                response = response.rsplit("```", 1)[0]
            response = response.strip()

            actions_data = json.loads(response)
            actions = []
            for a in actions_data:
                actions.append(BrowserAction(
                    step=a.get("step", len(actions) + 1),
                    action=a.get("action", ""),
                    target=a.get("target", ""),
                    description=a.get("description", ""),
                ))

            logger.info(f"Planned {len(actions)} browser actions")
            return actions

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse action plan: {e}")
            # Fallback: try simple intent parsing
            return await self._simple_plan(request)

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return []

    async def _simple_plan(self, request: str) -> list[BrowserAction]:
        """
        Fallback planner for when LLM planning fails.
        Uses keyword matching for common requests.
        """
        request_lower = request.lower()
        actions = []

        if "youtube" in request_lower and any(w in request_lower for w in ["play", "search", "find", "watch"]):
            # Extract the query part
            for prefix in ["play", "search", "find", "watch", "open"]:
                if prefix in request_lower:
                    query = request_lower.split(prefix, 1)[-1].replace("on youtube", "").replace("youtube", "").strip()
                    if query:
                        actions.append(BrowserAction(
                            step=1, action="youtube_play", target=query,
                            description=f"Play '{query}' on YouTube",
                        ))
                        return actions

        if any(w in request_lower for w in ["open", "go to", "navigate"]):
            # Extract URL or site name
            for prefix in ["open", "go to", "navigate to", "visit"]:
                if prefix in request_lower:
                    target = request_lower.split(prefix, 1)[-1].strip()
                    # Map common site names to URLs
                    site_map = {
                        "youtube": "https://www.youtube.com",
                        "google": "https://www.google.com",
                        "github": "https://github.com",
                        "reddit": "https://www.reddit.com",
                        "twitter": "https://twitter.com",
                        "x": "https://x.com",
                        "gmail": "https://mail.google.com",
                        "chatgpt": "https://chatgpt.com",
                        "gemini": "https://gemini.google.com",
                    }
                    url = site_map.get(target, target)
                    if not url.startswith("http"):
                        url = f"https://www.{url}.com" if "." not in url else f"https://{url}"

                    actions.append(BrowserAction(
                        step=1, action="navigate", target=url,
                        description=f"Open {target}",
                    ))
                    return actions

        if any(w in request_lower for w in ["search", "google", "look up", "find"]):
            query = request_lower
            for prefix in ["search for", "search", "google", "look up", "find"]:
                query = query.replace(prefix, "").strip()
            if query:
                actions.append(BrowserAction(
                    step=1, action="search_google", target=query,
                    description=f"Search Google for '{query}'",
                ))
                return actions

        if "close" in request_lower and "tab" in request_lower:
            if "all" in request_lower:
                actions.append(BrowserAction(
                    step=1, action="close_all_tabs", target="all",
                    description="Close all browser tabs",
                ))
            else:
                actions.append(BrowserAction(
                    step=1, action="close_tab", target="current",
                    description="Close current tab",
                ))
            return actions

        if "summarize" in request_lower and ("page" in request_lower or "this" in request_lower):
            actions.append(BrowserAction(
                step=1, action="extract", target="full",
                description="Extract page content for summarization",
            ))
            return actions

        return actions

    async def _execute_action(self, action: BrowserAction) -> str:
        """Execute a single browser action."""
        ctrl = self.controller
        a = action.action
        t = action.target

        if a == "navigate":
            ok = await ctrl.navigate(t)
            await ctrl.wait_seconds(1)
            return f"Navigated to {t}" if ok else "Navigation failed"

        elif a == "search_google":
            ok = await ctrl.search_google(t)
            await ctrl.wait_seconds(1.5)
            return f"Searched Google: {t}" if ok else "Search failed"

        elif a == "search_youtube":
            ok = await ctrl.search_youtube(t)
            await ctrl.wait_seconds(1.5)
            return f"Searched YouTube: {t}" if ok else "Search failed"

        elif a == "search_duckduckgo":
            ok = await ctrl.search_duckduckgo(t)
            await ctrl.wait_seconds(1.5)
            return f"Searched DuckDuckGo: {t}" if ok else "Search failed"

        elif a == "youtube_play":
            ok = await ctrl.youtube_play(t)
            return f"Playing: {t}" if ok else "YouTube play failed"

        elif a == "youtube_pause":
            await ctrl.youtube_pause()
            return "Toggled play/pause"

        elif a == "youtube_fullscreen":
            await ctrl.youtube_fullscreen()
            return "Toggled fullscreen"

        elif a == "youtube_volume":
            await ctrl.youtube_volume(t)
            return f"Volume adjusted {t}"

        elif a == "click_text":
            ok = await ctrl.click_text(t)
            await ctrl.wait_seconds(0.5)
            return f"Clicked: {t}" if ok else f"Could not find text: {t}"

        elif a == "click_button":
            ok = await ctrl.click_button(t)
            await ctrl.wait_seconds(0.5)
            return f"Clicked button: {t}" if ok else f"Button not found: {t}"

        elif a == "click_link":
            ok = await ctrl.click_link(t)
            await ctrl.wait_seconds(1)
            return f"Clicked link: {t}" if ok else f"Link not found: {t}"

        elif a == "type_text":
            parts = t.split("|||", 1)
            if len(parts) == 2:
                ok = await ctrl.type_text(parts[0], parts[1])
                return f"Typed text" if ok else "Type failed"
            return "Invalid type format"

        elif a == "type_and_enter":
            parts = t.split("|||", 1)
            if len(parts) == 2:
                ok = await ctrl.type_and_enter(parts[0], parts[1])
                return f"Typed and submitted" if ok else "Type+Enter failed"
            return "Invalid type format"

        elif a == "extract":
            content = await ctrl.get_page_content()
            if content:
                return content.text[:5000]  # Trim for LLM context
            return "No content extracted"

        elif a == "screenshot":
            full = t == "fullpage"
            data = await ctrl.screenshot(full_page=full)
            return f"Screenshot captured ({len(data)} bytes)" if data else "Screenshot failed"

        elif a == "new_tab":
            tab_id = await ctrl.new_tab(t if t else None)
            return f"Opened tab #{tab_id}"

        elif a == "close_tab":
            await ctrl.close_tab()
            return "Tab closed"

        elif a == "close_all_tabs":
            await ctrl.close_all_tabs()
            return "All tabs closed"

        elif a == "scroll":
            await ctrl.scroll(t)
            return f"Scrolled {t}"

        elif a == "press_key":
            await ctrl.press_key(t)
            return f"Pressed {t}"

        elif a == "wait":
            secs = float(t) if t else 1.0
            await ctrl.wait_seconds(secs)
            return f"Waited {secs}s"

        elif a == "go_back":
            await ctrl.go_back()
            return "Went back"

        else:
            return f"Unknown action: {a}"

    async def _should_continue_after_error(
        self, failed_action: BrowserAction, plan: list[BrowserAction], error: str
    ) -> bool:
        """Ask LLM if we should continue the plan after an error."""
        remaining = [a for a in plan if not a.completed and a.step > failed_action.step]
        if not remaining:
            return False

        try:
            response = await self.brain.quick_think(
                f"A browser automation step failed:\n"
                f"Step: {failed_action.description}\n"
                f"Error: {error}\n"
                f"Remaining steps: {[a.description for a in remaining]}\n\n"
                f"Should we continue with the remaining steps? Reply ONLY 'yes' or 'no'."
            )
            return "yes" in response.lower()
        except Exception:
            return False  # Default: stop on error

    async def _summarize_results(self, request: str, contents: list[str]) -> str:
        """Use LLM to summarize extracted content."""
        combined = "\n\n---\n\n".join(contents)
        # Trim to fit context
        if len(combined) > 10000:
            combined = combined[:10000] + "\n...[truncated]"

        try:
            response = await self.brain.think(
                f"Based on my browser research for: \"{request}\"\n\n"
                f"Here's what I found:\n{combined}\n\n"
                f"Please provide a clear, organized summary."
            )
            return response
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return combined[:2000]

    # ── Quick Commands (No LLM Needed) ──────────────────────────

    async def open_url(self, url: str) -> str:
        """Quick: Open a URL directly."""
        if not self.controller.is_launched:
            await self.controller.launch()
        ok = await self.controller.navigate(url)
        return f"Opened {url}" if ok else f"Failed to open {url}"

    async def search(self, query: str, engine: str = "google") -> str:
        """Quick: Run a search."""
        if not self.controller.is_launched:
            await self.controller.launch()

        if engine == "youtube":
            ok = await self.controller.search_youtube(query)
        elif engine == "duckduckgo":
            ok = await self.controller.search_duckduckgo(query)
        else:
            ok = await self.controller.search_google(query)

        return f"Searched {engine}: {query}" if ok else "Search failed"

    async def summarize_current_page(self) -> str:
        """Quick: Summarize whatever's on screen."""
        if not self.controller.is_launched:
            return "Browser is not open."

        content = await self.controller.get_page_content()
        if not content or not content.text:
            return "No content to summarize on the current page."

        return await self.brain.think(
            f"Summarize this web page concisely:\n\n"
            f"Title: {content.title}\n"
            f"URL: {content.url}\n\n"
            f"{content.text[:8000]}"
        )

    async def get_page_info(self) -> str:
        """Quick: Get info about the current page."""
        if not self.controller.is_launched:
            return "Browser is not open."

        context = await self.controller.get_context_summary()
        tabs = context["all_tabs"]
        active = context["active_tab"]

        lines = [f"**Active Tab:** {active['title']}"]
        lines.append(f"**URL:** {active['url']}")
        lines.append(f"**Total Tabs:** {len(tabs)}")
        if len(tabs) > 1:
            lines.append("\n**All Tabs:**")
            for t in tabs:
                marker = " ← active" if t["id"] == active["id"] else ""
                lines.append(f"  #{t['id']}: {t['title']} ({t['domain']}){marker}")

        return "\n".join(lines)

    async def close_browser(self) -> str:
        """Shutdown the browser completely."""
        await self.controller.shutdown()
        return "Browser closed."
