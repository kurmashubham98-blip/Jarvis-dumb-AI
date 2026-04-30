"""
Jarvis v2.0 — MemPalace Integration
======================================
Provides long-term memory for Jarvis using the MemPalace architecture.
Stores user preferences, factual data, past interactions, and knowledge graphs.

Features:
  - Verbatim dialog storage (ChromaDB)
  - Knowledge graph representation (SQLite)
  - Hall/Room/Drawer abstraction for contextual organization
"""

import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from jarvis.config import MEMORY_DIR

logger = logging.getLogger("jarvis.memory")


class JarvisMemory:
    """Wraps the MemPalace library to provide a clean API for Jarvis."""

    def __init__(self):
        self.db_path = str(MEMORY_DIR)
        self._palace = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy load MemPalace so it doesn't block startup."""
        if not self._initialized:
            try:
                # We import here so that if mempalace isn't installed yet,
                # the rest of Jarvis can still boot up in degraded memory mode.
                from mempalace.core.palace import Palace
                
                logger.info(f"Initializing MemPalace at {self.db_path}")
                # We'll create a dedicated "Jarvis_Core" wing for Jarvis's own mind
                self._palace = Palace(base_path=self.db_path)
                
                # Make sure the Jarvis wing exists
                if not getattr(self._palace, '_check_wing_exists', lambda w: True)("Jarvis_Core"):
                   pass  # Palace API handles auto-creation in newer versions usually
                   
                self._initialized = True
            except ImportError:
                logger.warning("MemPalace library not found. Running with amnesia.")
            except Exception as e:
                logger.error(f"Failed to initialize MemPalace: {e}")

    async def store_fact(self, room: str, drawer: str, item: str, metadata: dict = None) -> bool:
        """Store a factual piece of knowledge."""
        self._ensure_initialized()
        if not self._initialized:
            return False
            
        try:
            from mempalace.core.models import MemoryItem
            
            # Run in a thread since MemPalace is usually synchronous SQLite/Chroma ops
            def _store():
                self._palace.store(
                    wing="Jarvis_Core",
                    room=room or "General",
                    drawer=drawer or "Facts",
                    item=item,
                    metadata=metadata or {}
                )
                
            await asyncio.to_thread(_store)
            logger.debug(f"Stored fact in Jarvis_Core/{room}/{drawer}")
            return True
        except Exception as e:
            logger.error(f"Memory store failed: {e}")
            return False

    async def recall(self, query: str, room: str = None, drawer: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search for memories based on a query."""
        self._ensure_initialized()
        if not self._initialized:
            return []
            
        try:
            def _search():
                kwargs = {
                    "query": query,
                    "wing": "Jarvis_Core",
                    "n_results": limit
                }
                if room: kwargs["room"] = room
                if drawer: kwargs["drawer"] = drawer
                
                return self._palace.search(**kwargs)
                
            results = await asyncio.to_thread(_search)
            
            return [
                {
                    "content": res.content,
                    "metadata": res.metadata,
                    "distance": getattr(res, 'distance', 0.0)
                }
                for res in results
            ]
        except Exception as e:
            logger.error(f"Memory recall failed: {e}")
            return []

    async def add_to_knowledge_graph(self, subject: str, predicate: str, object_value: str) -> bool:
        """Add a directed relationship to the knowledge graph."""
        self._ensure_initialized()
        if not self._initialized:
            return False
            
        try:
            def _add():
                # Some versions of MemPalace have separate KnowledgeGraph modules
                if hasattr(self._palace, "knowledge_graph"):
                    self._palace.knowledge_graph.add_edge(subject, predicate, object_value)
                else:
                    # Fallback to standard storage
                    self._palace.store(
                        wing="Jarvis_Core",
                        room="KnowledgeGraph",
                        drawer=predicate,
                        item=f"{subject} {predicate} {object_value}",
                        metadata={"subject": subject, "predicate": predicate, "object": object_value}
                    )
                    
            await asyncio.to_thread(_add)
            return True
        except Exception as e:
            logger.error(f"Knowledge Graph update failed: {e}")
            return False
            
    async def store_conversation(self, prompt: str, response: str):
        """Store verbatim conversation history."""
        meta = {"type": "conversation"}
        # Truncate prompt to serve as a recognizable item handle
        item_summary = f"Q: {prompt[:50]}... A: {response[:50]}..."
        
        await self.store_fact(
            room="Verbatim",
            drawer="Conversation",
            item=item_summary,
            metadata={
                **meta,
                "full_prompt": prompt,
                "full_response": response
            }
        )

    def get_status(self) -> dict:
        return {
            "online": self._initialized,
            "db_path": self.db_path
        }
