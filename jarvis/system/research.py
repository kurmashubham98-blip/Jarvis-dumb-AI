"""
Jarvis v2.0 — Research Engine & News Filter
=============================================
Provides DuckDuckGo internet searches and news aggregation without API limits.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger("jarvis.system.research")


class ResearchEngine:
    """Performs web searches and news fetching using free libraries."""

    def __init__(self):
        pass

    async def search(self, query: str, max_results: int = 5) -> str:
        """
        Perform a DuckDuckGo web search.
        """
        try:
            from duckduckgo_search import DDGS
            import asyncio

            logger.info(f"Searching web for: {query}")
            
            def do_search():
                with DDGS() as ddgs:
                    results = [r for r in ddgs.text(query, max_results=max_results)]
                return results

            results = await asyncio.to_thread(do_search)
            
            if not results:
                return f"I couldn't find any information on '{query}'."

            summary_lines = [f"Search results for '{query}':"]
            for i, r in enumerate(results, 1):
                summary_lines.append(f"{i}. {r.get('title')} - {r.get('body')[:150]}...")

            return "\n\n".join(summary_lines)

        except ImportError:
            logger.error("duckduckgo_search not installed.")
            return "Web search module is offline. Missing duckduckgo-search package."
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"My connection to the search network was interrupted: {e}"

    async def fetch_news(self, topic: Optional[str] = None, max_results: int = 3) -> str:
        """Fetch latest news, optionally filtered by topic."""
        query = f"{topic} news" if topic else "world news headlines"
        try:
            from duckduckgo_search import DDGS
            import asyncio

            def do_news():
                with DDGS() as ddgs:
                    results = [r for r in ddgs.news(query, max_results=max_results)]
                return results

            results = await asyncio.to_thread(do_news)
            
            if not results:
                return f"I couldn't find any recent news for '{topic or 'general'}'."

            summary_lines = [f"Here are the latest headlines{' on ' + topic if topic else ''}:"]
            for i, r in enumerate(results, 1):
                source = r.get('source', 'Unknown source')
                title = r.get('title', 'Unknown title')
                summary_lines.append(f"{i}. {title} (Source: {source})")

            return "\n".join(summary_lines)

        except ImportError:
            return "News module offline."
        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            return "I was unable to retrieve the morning news."
