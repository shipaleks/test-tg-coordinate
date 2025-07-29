"""Synchronous wrapper for PostgreSQL database to match existing interface."""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from .postgres_db import get_postgres_db, PostgresDatabase

logger = logging.getLogger(__name__)


class PostgresSyncWrapper:
    """Synchronous wrapper for PostgreSQL database."""
    
    def __init__(self):
        """Initialize the wrapper."""
        self.db_path = "postgresql://railway"
        self._loop = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._db: Optional[PostgresDatabase] = None
        self._initialized = False
        
        # Initialize database on first use
        self._ensure_initialized()
    
    def _ensure_initialized(self):
        """Ensure database is initialized."""
        if not self._initialized:
            try:
                # Check if we're in async context (telegram bot handlers)
                try:
                    loop = asyncio.get_running_loop()
                    # We're in async context, can't use run_until_complete
                    # Mark as initialized and let first operation handle DB init
                    self._initialized = True
                    logger.info("PostgreSQL wrapper deferred initialization (async context)")
                    return
                except RuntimeError:
                    # No running loop, we can initialize normally
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    
                    # Initialize database
                    self._db = self._loop.run_until_complete(get_postgres_db())
                    self._initialized = True
                    logger.info("PostgreSQL sync wrapper initialized")
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL wrapper: {e}")
                raise
    
    def _run_async(self, coro):
        """Run async coroutine in sync context."""
        try:
            # Ensure database is initialized
            if self._db is None:
                # Get database asynchronously if needed
                import inspect
                if inspect.iscoroutine(coro):
                    # Create a wrapper to initialize DB first
                    async def wrapper():
                        if self._db is None:
                            self._db = await get_postgres_db()
                        return await coro
                    coro = wrapper()
            
            # Try to get current event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in async context, use create_task
                task = loop.create_task(coro)
                # Use run_in_executor to avoid blocking
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            except RuntimeError:
                # No running loop, create one
                return asyncio.run(coro)
                
        except Exception as e:
            logger.error(f"Error running async operation: {e}")
            raise
    
    def add_donation(
        self, 
        user_id: int, 
        payment_id: str, 
        stars_amount: int,
        telegram_username: Optional[str] = None,
        first_name: Optional[str] = None,
        invoice_payload: Optional[str] = None
    ) -> bool:
        """Add a new donation (sync)."""
        return self._run_async(
            self._db.add_donation(
                user_id, payment_id, stars_amount,
                telegram_username, first_name, invoice_payload
            )
        )
    
    def is_premium_user(self, user_id: int) -> bool:
        """Check if user has premium status (sync)."""
        return self._run_async(self._db.is_premium_user(user_id))
    
    def get_donor_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get donor information (sync)."""
        return self._run_async(self._db.get_donor_info(user_id))
    
    def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get donation history (sync)."""
        return self._run_async(self._db.get_donation_history(user_id))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics (sync)."""
        return self._run_async(self._db.get_stats())
    
    def get_user_language(self, user_id: int) -> str:
        """Get user language (sync)."""
        return self._run_async(self._db.get_user_language(user_id))
    
    def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user language (sync)."""
        return self._run_async(self._db.set_user_language(user_id, language))
    
    def has_language_set(self, user_id: int) -> bool:
        """Check if user has language set."""
        language = self.get_user_language(user_id)
        return language != "ru"  # ru is default
    
    def reset_user_language(self, user_id: int) -> bool:
        """Reset user language to default."""
        return self.set_user_language(user_id, "ru")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            if self._db and self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self._db.close())
            if self._executor:
                self._executor.shutdown(wait=False)
            if self._loop and not self._loop.is_closed():
                self._loop.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")