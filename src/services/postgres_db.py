"""PostgreSQL database for production deployment."""

import logging
import os
import time
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import asyncpg
from asyncpg.pool import Pool

logger = logging.getLogger(__name__)


class PostgresDatabase:
    """PostgreSQL database for managing donors."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize PostgreSQL connection."""
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        # Convert postgres:// to postgresql:// for compatibility
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)
        
        self.pool: Optional[Pool] = None
        self.db_path = f"postgresql://{self.database_url.split('@')[1]}"  # For display
    
    async def init(self):
        """Initialize connection pool and create tables."""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            
            # Create tables
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS donors (
                        user_id BIGINT PRIMARY KEY,
                        telegram_username TEXT,
                        first_name TEXT,
                        total_stars INTEGER DEFAULT 0,
                        first_donation_date BIGINT,
                        last_donation_date BIGINT,
                        premium_expires BIGINT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS donations (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES donors(user_id),
                        payment_id TEXT UNIQUE,
                        stars_amount INTEGER,
                        payment_date BIGINT,
                        invoice_payload TEXT
                    )
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id BIGINT PRIMARY KEY,
                        language TEXT DEFAULT 'ru',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Ensure reasoning column exists
                try:
                    await conn.execute(
                        "ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS reasoning TEXT DEFAULT 'low'"
                    )
                except Exception:
                    pass
                
                # Create indexes
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_user_id ON donations(user_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_payment_id ON donations(payment_id)")
                
            logger.info("PostgreSQL database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
    
    async def add_donation(
        self, 
        user_id: int, 
        payment_id: str, 
        stars_amount: int,
        telegram_username: Optional[str] = None,
        first_name: Optional[str] = None,
        invoice_payload: Optional[str] = None
    ) -> bool:
        """Add a new donation and update donor status."""
        try:
            current_time = int(time.time())
            
            async with self.pool.acquire() as conn:
                # Start transaction
                async with conn.transaction():
                    # Check if payment already exists
                    existing = await conn.fetchval(
                        "SELECT id FROM donations WHERE payment_id = $1", 
                        payment_id
                    )
                    
                    if existing:
                        logger.warning(f"Payment {payment_id} already exists")
                        return False
                    
                    # First ensure donor exists
                    donor = await conn.fetchrow(
                        "SELECT total_stars FROM donors WHERE user_id = $1",
                        user_id
                    )
                    
                    if donor:
                        # Update existing donor
                        new_total = donor['total_stars'] + stars_amount
                        await conn.execute("""
                            UPDATE donors 
                            SET total_stars = $2, 
                                last_donation_date = $3, 
                                telegram_username = $4, 
                                first_name = $5,
                                premium_expires = $6
                            WHERE user_id = $1
                        """, user_id, new_total, current_time, telegram_username, 
                            first_name, current_time + (25 * 365 * 24 * 60 * 60))
                    else:
                        # Create new donor first (before adding donation due to foreign key)
                        await conn.execute("""
                            INSERT INTO donors 
                            (user_id, telegram_username, first_name, total_stars, 
                             first_donation_date, last_donation_date, premium_expires)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, user_id, telegram_username, first_name, stars_amount, 
                            current_time, current_time, current_time + (25 * 365 * 24 * 60 * 60))
                    
                    # Now add donation (after donor exists)
                    await conn.execute("""
                        INSERT INTO donations (user_id, payment_id, stars_amount, payment_date, invoice_payload)
                        VALUES ($1, $2, $3, $4, $5)
                    """, user_id, payment_id, stars_amount, current_time, invoice_payload)
                    
                    logger.info(f"Added donation: user_id={user_id}, stars={stars_amount}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to add donation: {e}")
            return False
    
    async def is_premium_user(self, user_id: int) -> bool:
        """Check if user has active premium status."""
        try:
            current_time = int(time.time())
            
            async with self.pool.acquire() as conn:
                result = await conn.fetchval("""
                    SELECT premium_expires FROM donors 
                    WHERE user_id = $1 AND premium_expires > $2
                """, user_id, current_time)
                
                return result is not None
                
        except Exception as e:
            logger.error(f"Failed to check premium status: {e}")
            return False
    
    async def get_donor_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get donor information."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT user_id, telegram_username, first_name, total_stars, 
                           first_donation_date, last_donation_date, premium_expires
                    FROM donors WHERE user_id = $1
                """, user_id)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get donor info: {e}")
            return None
    
    async def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get donation history for a user."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT payment_id, stars_amount, payment_date, invoice_payload
                    FROM donations 
                    WHERE user_id = $1
                    ORDER BY payment_date DESC
                """, user_id)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get donation history: {e}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            current_time = int(time.time())
            
            async with self.pool.acquire() as conn:
                # Use single query for efficiency
                stats = await conn.fetchrow("""
                    SELECT 
                        (SELECT COUNT(*) FROM donors) as total_donors,
                        (SELECT COUNT(*) FROM donations) as total_donations,
                        (SELECT COALESCE(SUM(stars_amount), 0) FROM donations) as total_stars,
                        (SELECT COUNT(*) FROM donors WHERE premium_expires > $1) as active_premium,
                        (SELECT COUNT(*) FROM user_preferences) as users_with_language
                """, current_time)
                
                return dict(stats) if stats else {}
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    
    async def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language."""
        try:
            async with self.pool.acquire() as conn:
                language = await conn.fetchval(
                    "SELECT language FROM user_preferences WHERE user_id = $1",
                    user_id
                )
                return language or "ru"
                
        except Exception as e:
            logger.error(f"Failed to get user language: {e}")
            return "ru"
    
    async def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user's preferred language."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_preferences (user_id, language, updated_at)
                    VALUES ($1, $2, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET language = $2, updated_at = CURRENT_TIMESTAMP
                """, user_id, language)
                
                logger.info(f"Set language {language} for user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to set language: {e}")
            return False

    async def has_language_set(self, user_id: int) -> bool:
        """Check if user has an explicit language preference set."""
        try:
            async with self.pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT 1 FROM user_preferences WHERE user_id = $1",
                    user_id,
                )
                return exists is not None
        except Exception as e:
            logger.error(f"Failed to check language presence: {e}")
            return False

    async def reset_user_language(self, user_id: int) -> bool:
        """Delete user's language preference to force selection on /start."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM user_preferences WHERE user_id = $1",
                    user_id,
                )
                logger.info(f"Reset language preference for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to reset user language: {e}")
            return False

    async def get_user_reasoning(self, user_id: int) -> str:
        """Get user's preferred reasoning effort (minimal/low/medium/high)."""
        try:
            async with self.pool.acquire() as conn:
                level = await conn.fetchval(
                    "SELECT reasoning FROM user_preferences WHERE user_id = $1",
                    user_id,
                )
                return (level or "minimal").strip()
        except Exception as e:
            logger.error(f"Failed to get user reasoning: {e}")
            return "minimal"

    async def set_user_reasoning(self, user_id: int, level: str) -> bool:
        """Set user's preferred reasoning effort (minimal/low/medium/high)."""
        try:
            async with self.pool.acquire() as conn:
                # Preserve existing language if present
                await conn.execute(
                    """
                    INSERT INTO user_preferences (user_id, language, reasoning, updated_at)
                    VALUES ($1, COALESCE((SELECT language FROM user_preferences WHERE user_id=$1), 'ru'), $2, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id)
                    DO UPDATE SET reasoning = $2, updated_at = CURRENT_TIMESTAMP
                    """,
                    user_id,
                    level,
                )
                logger.info(f"Set reasoning {level} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to set user reasoning: {e}")
            return False


# Global instance
_postgres_db: Optional[PostgresDatabase] = None


async def get_postgres_db() -> PostgresDatabase:
    """Get or create PostgreSQL database instance."""
    global _postgres_db
    if _postgres_db is None:
        _postgres_db = PostgresDatabase()
        await _postgres_db.init()
    return _postgres_db