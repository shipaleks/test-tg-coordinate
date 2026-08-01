"""Async wrapper for database operations to handle both PostgreSQL and SQLite."""

import asyncio
import inspect
import logging
import os
from typing import Any

from .donors_db import DonorsDatabase
from .postgres_db import PostgresDatabase, get_postgres_db

logger = logging.getLogger(__name__)

# Forward-maps model IDs persisted in user rows to the current lineup.
# Rows are permanent: DB reads go through this mapping forever, so every
# ID that was ever offered in /reason (or shipped as a default) needs an
# entry pointing at a currently-served model.
MODEL_MAPPING = {
    # Legacy OpenAI models → Claude
    "gpt-5": "claude-opus-5",
    "gpt-5.1": "claude-opus-5",
    "gpt-5-mini": "claude-opus-5",
    "gpt-5.1-mini": "claude-sonnet-5",
    # Previous Claude models → current
    "claude-opus-4-5-20251101": "claude-opus-5",
    "claude-opus-4-6": "claude-opus-5",
    "claude-sonnet-4-5-20250929": "claude-sonnet-5",
    # Claude model aliases
    "claude-opus": "claude-opus-5",
    "claude-sonnet": "claude-sonnet-5",
}


class AsyncDonorsWrapper:
    """Unified async interface for both PostgreSQL and SQLite databases."""

    def __init__(self):
        self._db: DonorsDatabase | PostgresDatabase | Any | None = None
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

    async def _call_db(self, method_name: str, *args: Any) -> Any:
        """Dispatch a call to the active backend without blocking the loop.

        Postgres methods are native coroutines and are awaited directly;
        the SQLite and Firestore backends do blocking I/O, so their calls
        run in a worker thread.
        """
        await self._ensure_initialized()
        method = getattr(self._db, method_name)
        if inspect.iscoroutinefunction(method):
            return await method(*args)
        return await asyncio.to_thread(method, *args)

    async def add_donation(
        self,
        user_id: int,
        payment_id: str,
        stars_amount: int,
        telegram_username: str | None = None,
        first_name: str | None = None,
        invoice_payload: str | None = None,
    ) -> bool:
        """Add donation (async)."""
        return await self._call_db(
            "add_donation",
            user_id,
            payment_id,
            stars_amount,
            telegram_username,
            first_name,
            invoice_payload,
        )

    async def is_premium_user(self, user_id: int) -> bool:
        """Check premium status (async)."""
        return await self._call_db("is_premium_user", user_id)

    async def get_donor_info(self, user_id: int) -> dict[str, Any] | None:
        """Get donor info (async)."""
        return await self._call_db("get_donor_info", user_id)

    async def get_donation_history(self, user_id: int) -> list[dict[str, Any]]:
        """Get donation history (async)."""
        return await self._call_db("get_donation_history", user_id)

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics (async)."""
        return await self._call_db("get_stats")

    async def get_user_language(self, user_id: int) -> str:
        """Get user language (async)."""
        return await self._call_db("get_user_language", user_id)

    async def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user language (async)."""
        return await self._call_db("set_user_language", user_id, language)

    async def has_language_set(self, user_id: int) -> bool:
        """Check if language is set (async)."""
        try:
            return await self._call_db("has_language_set", user_id)
        except Exception as e:
            # If we cannot check explicitly, default to False so the menu is shown
            logger.warning(
                f"has_language_set check failed for user {user_id}: {e}. Defaulting to False."
            )
            return False

    async def reset_user_language(self, user_id: int) -> bool:
        """Reset language (async)."""
        try:
            return await self._call_db("reset_user_language", user_id)
        except Exception:
            return await self.set_user_language(user_id, "ru")

    async def get_user_reasoning(self, user_id: int) -> str:
        """Get user's preferred reasoning level (async).

        Auto-upgrades donors from 'none' to 'low' as a bonus reward.
        """
        level = await self._call_db("get_user_reasoning", user_id)

        # Map legacy reasoning levels (for backward compatibility)
        REASONING_MAPPING = {
            "minimal": "low",  # Legacy minimal → low
            # Keep current levels as-is
            "none": "none",
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        mapped_level = REASONING_MAPPING.get(level, level)

        # BONUS: Auto-upgrade donors from 'none' to 'low' (hidden reward)
        if mapped_level == "none":
            try:
                is_donor = await self.is_premium_user(user_id)
                if is_donor:
                    return "low"  # Donors get better reasoning automatically
            except Exception:
                pass

        return mapped_level

    async def set_user_reasoning(self, user_id: int, level: str) -> bool:
        """Set user's preferred reasoning level (async)."""
        return await self._call_db("set_user_reasoning", user_id, level)

    async def get_user_model(self, user_id: int) -> str:
        model = await self._call_db("get_user_model", user_id)

        # Map legacy model names to current Claude models
        return MODEL_MAPPING.get(model, model)  # Return mapped or original

    async def set_user_model(self, user_id: int, model: str) -> bool:
        return await self._call_db("set_user_model", user_id, model)


# Global instance
_async_db: AsyncDonorsWrapper | None = None


async def get_async_donors_db() -> AsyncDonorsWrapper:
    """Get async database wrapper."""
    global _async_db
    if _async_db is None:
        _async_db = AsyncDonorsWrapper()
        await _async_db._ensure_initialized()
    return _async_db
