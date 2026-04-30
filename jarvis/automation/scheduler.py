"""
Jarvis v2.0 — Task Scheduler
==============================
Handles periodic and scheduled background tasks.
Powered by APScheduler.
"""

import logging
from datetime import datetime
from typing import Callable, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("jarvis.automation.scheduler")


class JarvisScheduler:
    """Manages timed and recurring jobs."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.jobs = {}
        
    def start(self):
        """Start the background scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Task scheduler started")

    def stop(self):
        """Stop the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Task scheduler stopped")

    def add_interval_job(self, func: Callable, seconds: int, job_id: str, *args, **kwargs) -> bool:
        """Run a function periodically."""
        try:
            job = self.scheduler.add_job(
                func,
                trigger=IntervalTrigger(seconds=seconds),
                id=job_id,
                replace_existing=True,
                args=args,
                kwargs=kwargs
            )
            self.jobs[job_id] = job
            logger.debug(f"Added interval job: {job_id} ({seconds}s)")
            return True
        except Exception as e:
            logger.error(f"Failed to add interval job {job_id}: {e}")
            return False

    def add_cron_job(self, func: Callable, job_id: str, hour: Optional[str] = None, minute: Optional[str] = None, *args, **kwargs) -> bool:
        """Run a function at specific times (e.g., 9:00 AM daily)."""
        try:
            job = self.scheduler.add_job(
                func,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=job_id,
                replace_existing=True,
                args=args,
                kwargs=kwargs
            )
            self.jobs[job_id] = job
            logger.info(f"Added cron job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add cron job {job_id}: {e}")
            return False

    def remove_job(self, job_id: str):
        """Remove a scheduled job."""
        if job_id in self.jobs:
            self.scheduler.remove_job(job_id)
            del self.jobs[job_id]
            logger.info(f"Removed job: {job_id}")
            
    def get_status(self) -> dict:
        return {
            "running": self.scheduler.running,
            "jobs_count": len(self.jobs),
            "active_jobs": list(self.jobs.keys())
        }
