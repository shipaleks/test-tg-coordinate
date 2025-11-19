"""Async wrapper for database operations to handle both PostgreSQL and SQLite."""

import os
import logging
from typing import Optional, List, Dict, Any, Union

from .donors_db import DonorsDatabase
from .postgres_db import PostgresDatabase, get_postgres_db

logger = logging.getLogger(__name__)


class AsyncDonorsWrapper:
    """Unified async interface for both PostgreSQL and SQLite databases."""
    
    def __init__(self):
        self._db: Optional[Union[DonorsDatabase, PostgresDatabase, Any]] = None
        self._is_postgres = bool(os.environ.get("DATABASE_URL"))
        self._use_firestore = os.environ.get("USE_FIRESTORE_DB", "").lower() == "true"

        self._initialized = False
    
    async def _ensure_initialized(self):
        """Ensure database is initialized."""
        if not self._initialized:
            if self._use_firestore:
                from .firebase_db import FirestoreDatabase
                self._db = FirestoreDatabase()
                self.db_path = self._db.db_path
            elif self._is_postgres:
                self._db = await get_postgres_db()
                self.db_path = self._db.db_path
            else:
                # Use regular SQLite database
                from .donors_db import DonorsDatabase
                self._db = DonorsDatabase()
                self.db_path = self._db.db_path
            self._initialized = True
    
    async def add_donation(
        self, 
        user_id: int, 
        payment_id: str, 
        stars_amount: int,
        telegram_username: Optional[str] = None,
        first_name: Optional[str] = None,
        invoice_payload: Optional[str] = None
    ) -> bool:
        """Add donation (async)."""
        await self._ensure_initialized()
        
        if self._use_firestore or self._is_postgres:
            return await self._db.add_donation(
                user_id, payment_id, stars_amount,
                telegram_username, first_name, invoice_payload
            )
        else:
            return self._db.add_donation(
                user_id, payment_id, stars_amount,
                telegram_username, first_name, invoice_payload
            )
    
    async def is_premium_user(self, user_id: int) -> bool:
        """Check premium status (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.is_premium_user(user_id)
        else:
            return self._db.is_premium_user(user_id)
    
    async def get_donor_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get donor info (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.get_donor_info(user_id)
        else:
            return self._db.get_donor_info(user_id)
    
    async def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get donation history (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.get_donation_history(user_id)
        else:
            return self._db.get_donation_history(user_id)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.get_stats()
        else:
            return self._db.get_stats()
    
    async def get_user_language(self, user_id: int) -> str:
        """Get user language (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.get_user_language(user_id)
        else:
            return self._db.get_user_language(user_id)
    
    async def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user language (async)."""
        await self._ensure_initialized()
        
        if self._is_postgres:
            return await self._db.set_user_language(user_id, language)
        else:
            return self._db.set_user_language(user_id, language)
    
    async def has_language_set(self, user_id: int) -> bool:
        """Check if language is set (async)."""
        await self._ensure_initialized()
        if self._is_postgres:
            try:
                return await self._db.has_language_set(user_id)  # type: ignore[attr-defined]
            except Exception as e:
                # If we cannot check explicitly, default to False so the menu is shown
                logger.warning(f"Postgres has_language_set check failed for user {user_id}: {e}. Defaulting to False.")
                return False
        else:
            return self._db.has_language_set(user_id)  # type: ignore[attr-defined]
    
    async def reset_user_language(self, user_id: int) -> bool:
        """Reset language (async)."""
        await self._ensure_initialized()
        if self._is_postgres:
            try:
                return await self._db.reset_user_language(user_id)  # type: ignore[attr-defined]
            except Exception:
                return await self.set_user_language(user_id, "ru")
        else:
            return self._db.reset_user_language(user_id)  # type: ignore[attr-defined]

    async def get_user_reasoning(self, user_id: int) -> str:
        """Get user's preferred reasoning level (async)."""
        await self._ensure_initialized()
        if self._is_postgres:
            level = await self._db.get_user_reasoning(user_id)  # type: ignore[attr-defined]
        else:
            level = self._db.get_user_reasoning(user_id)  # type: ignore[attr-defined]
        
        # Map legacy reasoning levels (for backward compatibility)
        REASONING_MAPPING = {
            "minimal": "low",  # Legacy minimal → low
            # Keep current levels as-is
            "none": "none",
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return REASONING_MAPPING.get(level, level)  # Return mapped or original

    async def set_user_reasoning(self, user_id: int, level: str) -> bool:
        """Set user's preferred reasoning level (async)."""
        await self._ensure_initialized()
        if self._is_postgres:
            return await self._db.set_user_reasoning(user_id, level)  # type: ignore[attr-defined]
        else:
            return self._db.set_user_reasoning(user_id, level)  # type: ignore[attr-defined]

    async def get_user_model(self, user_id: int) -> str:
        await self._ensure_initialized()
        if self._is_postgres:
            model = await self._db.get_user_model(user_id)  # type: ignore[attr-defined]
        else:
            model = self._db.get_user_model(user_id)  # type: ignore[attr-defined]
        
        # Map legacy model names to current versions (future-proof)
        MODEL_MAPPING = {
            "gpt-5": "gpt-5.1",
            "gpt-5-mini": "gpt-5.1-mini",
            # Future mappings can be added here:
            # "gpt-5.1": "gpt-5.2" (when available)
        }
        return MODEL_MAPPING.get(model, model)  # Return mapped or original

    async def set_user_model(self, user_id: int, model: str) -> bool:
        await self._ensure_initialized()
        if self._is_postgres:
            return await self._db.set_user_model(user_id, model)  # type: ignore[attr-defined]
        else:
            return self._db.set_user_model(user_id, model)  # type: ignore[attr-defined]


# Global instance
_async_db: Optional[AsyncDonorsWrapper] = None


async def get_async_donors_db() -> AsyncDonorsWrapper:
    """Get async database wrapper."""
    global _async_db
    if _async_db is None:
        _async_db = AsyncDonorsWrapper()
        await _async_db._ensure_initialized()
    return _async_db