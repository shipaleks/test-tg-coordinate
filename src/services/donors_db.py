"""Database service for managing donors and their premium status."""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class DonorsDatabase:
    """SQLite database for managing donors and their premium access."""
    
    def __init__(self, db_path: str = None):
        """Initialize the donors database.
        
        Args:
            db_path: Path to the SQLite database file. If None, uses environment or default path.
        """
        if db_path is None:
            # Use Railway volume path if available, otherwise default
            import os
            volume_path = "/data"
            if os.path.exists(volume_path) and os.access(volume_path, os.W_OK):
                db_path = os.path.join(volume_path, "donors.db")
                logger.info(f"Using Railway volume for database: {db_path}")
            else:
                db_path = "donors.db"
                logger.info(f"Using local database: {db_path}")
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_database()
        
    def _init_database(self):
        """Initialize the database schema."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS donors (
                            user_id INTEGER PRIMARY KEY,
                            telegram_username TEXT,
                            first_name TEXT,
                            total_stars INTEGER DEFAULT 0,
                            first_donation_date INTEGER,
                            last_donation_date INTEGER,
                            premium_expires INTEGER DEFAULT 0,
                            created_at INTEGER DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS donations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            payment_id TEXT UNIQUE,
                            stars_amount INTEGER,
                            payment_date INTEGER,
                            invoice_payload TEXT,
                            FOREIGN KEY (user_id) REFERENCES donors (user_id)
                        )
                    """)
                    
                    # User preferences table for language settings
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_preferences (
                            user_id INTEGER PRIMARY KEY,
                            language TEXT DEFAULT 'ru',
                            created_at INTEGER DEFAULT CURRENT_TIMESTAMP,
                            updated_at INTEGER DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Create indexes for better performance
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_donors_user_id ON donors (user_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_user_id ON donations (user_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_payment_id ON donations (payment_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences (user_id)")
                    
                    conn.commit()
                    logger.info("Donors database initialized successfully")
                    
        except Exception as e:
            logger.error(f"Failed to initialize donors database: {e}")
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
        """Add a new donation and update donor status.
        
        Args:
            user_id: Telegram user ID
            payment_id: Unique payment identifier from Telegram
            stars_amount: Amount of stars donated
            telegram_username: User's Telegram username
            first_name: User's first name
            invoice_payload: Invoice payload for tracking
            
        Returns:
            True if donation was added successfully, False otherwise
        """
        try:
            current_time = int(time.time())
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Check if payment already exists (prevent double processing)
                    existing = conn.execute(
                        "SELECT id FROM donations WHERE payment_id = ?", 
                        (payment_id,)
                    ).fetchone()
                    
                    if existing:
                        logger.warning(f"Payment {payment_id} already exists in database")
                        return False
                    
                    # Add donation record
                    conn.execute("""
                        INSERT INTO donations (user_id, payment_id, stars_amount, payment_date, invoice_payload)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, payment_id, stars_amount, current_time, invoice_payload))
                    
                    # Update or create donor record
                    donor = conn.execute(
                        "SELECT total_stars, first_donation_date FROM donors WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()
                    
                    if donor:
                        # Update existing donor
                        new_total = donor[0] + stars_amount
                        conn.execute("""
                            UPDATE donors 
                            SET total_stars = ?, last_donation_date = ?, telegram_username = ?, first_name = ?
                            WHERE user_id = ?
                        """, (new_total, current_time, telegram_username, first_name, user_id))
                    else:
                        # Create new donor
                        conn.execute("""
                            INSERT INTO donors 
                            (user_id, telegram_username, first_name, total_stars, first_donation_date, last_donation_date)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (user_id, telegram_username, first_name, stars_amount, current_time, current_time))
                    
                    # Calculate and update premium expiration
                    self._update_premium_status(conn, user_id, stars_amount)
                    
                    conn.commit()
                    logger.info(f"Added donation: user_id={user_id}, stars={stars_amount}, payment_id={payment_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to add donation: {e}")
            return False
    
    def _update_premium_status(self, conn: sqlite3.Connection, user_id: int, stars_amount: int):
        """Update premium status based on donation amount.
        
        Args:
            conn: Database connection
            user_id: User ID
            stars_amount: Amount of stars donated
        """
        # Set permanent premium status for any donor (hidden bonus)
        # Using a far future timestamp (year 2050) to indicate permanent status
        permanent_expires = int(time.time()) + (25 * 365 * 24 * 60 * 60)  # 25 years from now
        
        conn.execute(
            "UPDATE donors SET premium_expires = ? WHERE user_id = ?",
            (permanent_expires, user_id)
        )
        
        logger.info(f"Granted permanent enhanced access for donor {user_id} (hidden bonus)")
    
    def is_premium_user(self, user_id: int) -> bool:
        """Check if user has active premium status.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user has active premium, False otherwise
        """
        try:
            current_time = int(time.time())
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    result = conn.execute(
                        "SELECT premium_expires FROM donors WHERE user_id = ? AND premium_expires > ?",
                        (user_id, current_time)
                    ).fetchone()
                    
                    return result is not None
                    
        except Exception as e:
            logger.error(f"Failed to check premium status for user {user_id}: {e}")
            return False
    
    def get_donor_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get donor information.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with donor info or None if not found
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    result = conn.execute("""
                        SELECT user_id, telegram_username, first_name, total_stars, 
                               first_donation_date, last_donation_date, premium_expires
                        FROM donors WHERE user_id = ?
                    """, (user_id,)).fetchone()
                    
                    if result:
                        return dict(result)
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get donor info for user {user_id}: {e}")
            return None
    
    def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get donation history for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List of donation records
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    results = conn.execute("""
                        SELECT payment_id, stars_amount, payment_date, invoice_payload
                        FROM donations 
                        WHERE user_id = ?
                        ORDER BY payment_date DESC
                    """, (user_id,)).fetchall()
                    
                    return [dict(row) for row in results]
                    
        except Exception as e:
            logger.error(f"Failed to get donation history for user {user_id}: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            current_time = int(time.time())
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Total donors
                    total_donors = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
                    
                    # Total donations
                    total_donations = conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0]
                    
                    # Total stars collected
                    total_stars = conn.execute("SELECT SUM(stars_amount) FROM donations").fetchone()[0] or 0
                    
                    # Active premium users
                    active_premium = conn.execute(
                        "SELECT COUNT(*) FROM donors WHERE premium_expires > ?",
                        (current_time,)
                    ).fetchone()[0]
                    
                    # Total users with language preferences
                    users_with_language = conn.execute("SELECT COUNT(*) FROM user_preferences").fetchone()[0]
                    
                    return {
                        "total_donors": total_donors,
                        "total_donations": total_donations,
                        "total_stars": total_stars,
                        "active_premium": active_premium,
                        "users_with_language": users_with_language
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Language code (defaults to 'ru' if not set)
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    result = conn.execute(
                        "SELECT language FROM user_preferences WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()
                    
                    if result:
                        return result[0]
                    return "ru"  # Default to Russian
                    
        except Exception as e:
            logger.error(f"Failed to get user language for user {user_id}: {e}")
            return "ru"  # Default fallback
    
    def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user's preferred language.
        
        Args:
            user_id: Telegram user ID
            language: Language code (e.g., 'en', 'ru', 'fr', etc.)
            
        Returns:
            True if language was set successfully, False otherwise
        """
        try:
            current_time = int(time.time())
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Use INSERT OR REPLACE to handle both new and existing users
                    conn.execute("""
                        INSERT OR REPLACE INTO user_preferences (user_id, language, updated_at)
                        VALUES (?, ?, ?)
                    """, (user_id, language, current_time))
                    
                    conn.commit()
                    logger.info(f"Set language {language} for user {user_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to set language for user {user_id}: {e}")
            return False
    
    def has_language_set(self, user_id: int) -> bool:
        """Check if user has a language preference set.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user has language set, False otherwise
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    result = conn.execute(
                        "SELECT 1 FROM user_preferences WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()
                    
                    return result is not None
                    
        except Exception as e:
            logger.error(f"Failed to check language status for user {user_id}: {e}")
            return False
    
    def reset_user_language(self, user_id: int) -> bool:
        """Reset user's language preference (delete from database).
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if reset successfully, False otherwise
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM user_preferences WHERE user_id = ?",
                        (user_id,)
                    )
                    
                    conn.commit()
                    logger.info(f"Reset language preference for user {user_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to reset language for user {user_id}: {e}")
            return False


# Global database instance - will be initialized lazily
_donors_db: Optional[DonorsDatabase] = None


def get_donors_db() -> DonorsDatabase:
    """Get or create the global donors database instance."""
    global _donors_db
    if _donors_db is None:
        _donors_db = DonorsDatabase()
    return _donors_db