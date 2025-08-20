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
            
            # Check if we're running on Railway (multiple detection methods)
            is_railway = (
                os.environ.get("RAILWAY_ENVIRONMENT") is not None or
                os.environ.get("RAILWAY_ENVIRONMENT_NAME") is not None or
                os.environ.get("RAILWAY_PROJECT_ID") is not None or
                os.environ.get("RAILWAY_SERVICE_ID") is not None or
                os.environ.get("RAILWAY_VOLUME_ID") is not None
            )
            
            # Allow forcing volume path via environment variable
            force_volume = os.environ.get("FORCE_VOLUME_PATH", "").lower() == "true"
            
            # Check for custom volume path from environment variable
            # Use Railway's official volume mount path first, then fallback to custom or default
            volume_path = (
                os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or 
                os.environ.get("VOLUME_PATH") or 
                "/data"
            )
            
            logger.info(f"Detected volume path: {volume_path}")
            
            # Simplified path selection logic
            if is_railway:
                # On Railway, try volume path first, then fallback to writable app directory
                if os.path.exists(volume_path) and os.access(volume_path, os.W_OK):
                    db_path = os.path.join(volume_path, "donors.db")
                    logger.info(f"Using Railway volume for database: {db_path}")
                else:
                    # Try to create subdirectory in volume, if that fails use /tmp
                    if os.path.exists(volume_path):
                        try:
                            # Try creating subdirectory in volume with different permissions
                            import subprocess
                            subprocess.run(['mkdir', '-p', f'{volume_path}/appdata'], check=False)
                            subprocess.run(['chmod', '777', f'{volume_path}/appdata'], check=False)
                            
                            app_volume_dir = os.path.join(volume_path, "appdata")
                            if os.path.exists(app_volume_dir):
                                db_path = os.path.join(app_volume_dir, "donors.db")
                                logger.info(f"Using volume subdirectory: {db_path}")
                            else:
                                raise Exception("Could not create volume subdirectory")
                        except Exception as subdir_error:
                            logger.warning(f"Could not create volume subdirectory: {subdir_error}")
                            # Fallback to /tmp (temporary but writable)
                            app_data_dir = "/tmp/railway_data"
                            os.makedirs(app_data_dir, exist_ok=True) 
                            db_path = os.path.join(app_data_dir, "donors.db")
                            logger.warning(f"Using temporary /tmp directory: {db_path} (NOT PERSISTENT!)")
                    else:
                        # Volume doesn't exist, use /tmp
                        app_data_dir = "/tmp/railway_data"
                        os.makedirs(app_data_dir, exist_ok=True)
                        db_path = os.path.join(app_data_dir, "donors.db")
                        logger.warning(f"Volume not found, using /tmp: {db_path} (NOT PERSISTENT!)")
            else:
                # Local development
                db_path = "donors.db"
                logger.info(f"Using local database: {db_path}")
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_database()
        
    def _init_database(self):
        """Initialize the database schema."""
        try:
            with self._lock:
                # Try to create/connect to the database
                try:
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
                            language TEXT DEFAULT 'en',
                            reasoning TEXT DEFAULT 'low',
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
                        
                except Exception as volume_error:
                    logger.error(f"Failed to initialize database at {self.db_path}: {volume_error}")
                    
                    # If we were trying to use volume but failed, fallback to local database
                    if "/data" in str(self.db_path):
                        logger.info("Falling back to local database due to volume error")
                        self.db_path = Path("donors.db")
                        
                        # Retry with local database
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
                            
                            conn.execute("""
                                CREATE TABLE IF NOT EXISTS user_preferences (
                                    user_id INTEGER PRIMARY KEY,
                                    language TEXT DEFAULT 'en',
                                    reasoning TEXT DEFAULT 'low',
                                    created_at INTEGER DEFAULT CURRENT_TIMESTAMP,
                                    updated_at INTEGER DEFAULT CURRENT_TIMESTAMP
                                )
                            """)
                            
                            # Create indexes
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_donors_user_id ON donors (user_id)")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_user_id ON donations (user_id)")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_payment_id ON donations (payment_id)")
                            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences (user_id)")
                            
                            conn.commit()
                            logger.info("Fallback local database initialized successfully")
                    else:
                        raise volume_error
                        
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
                    # Default to Russian so that first-time users see language selection (wrapper checks ru)
                    return "ru"
                    
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
                    # Preserve existing reasoning if present
                    conn.execute("""
                        INSERT INTO user_preferences (user_id, language, reasoning, updated_at)
                        VALUES (?, ?, COALESCE((SELECT reasoning FROM user_preferences WHERE user_id = ?), 'minimal'), ?)
                        ON CONFLICT(user_id) DO UPDATE SET language=excluded.language, updated_at=excluded.updated_at
                    """, (user_id, language, user_id, current_time))
                    
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

    def get_user_reasoning(self, user_id: int) -> str:
        """Get user's preferred reasoning level (minimal/low/medium/high)."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    row = conn.execute(
                        "SELECT reasoning FROM user_preferences WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()
                    return (row[0] if row and row[0] else "minimal").strip()
        except Exception as e:
            logger.error(f"Failed to get user reasoning for user {user_id}: {e}")
            return "minimal"

    def set_user_reasoning(self, user_id: int, level: str) -> bool:
        """Set user's preferred reasoning level."""
        try:
            current_time = int(time.time())
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO user_preferences (user_id, language, reasoning, updated_at)
                        VALUES (?, COALESCE((SELECT language FROM user_preferences WHERE user_id = ?), 'ru'), ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET reasoning=excluded.reasoning, updated_at=excluded.updated_at
                        """,
                        (user_id, user_id, level, current_time)
                    )
                    conn.commit()
                    logger.info(f"Set reasoning {level} for user {user_id}")
                    return True
        except Exception as e:
            logger.error(f"Failed to set user reasoning for user {user_id}: {e}")
            return False


# Global database instance - will be initialized lazily
_donors_db: Optional[DonorsDatabase] = None


def get_donors_db() -> DonorsDatabase:
    """Get or create the global donors database instance."""
    global _donors_db
    if _donors_db is None:
        import os
        
        # Check for PostgreSQL database URL (Railway provides this)
        if os.environ.get("DATABASE_URL"):
            # Use PostgreSQL for production
            from .postgres_wrapper import PostgresSyncWrapper
            logger.info("Using PostgreSQL database (DATABASE_URL detected)")
            _donors_db = PostgresSyncWrapper()
        
        # Check if we should use environment-based database
        elif os.environ.get("USE_ENV_DB", "").lower() == "true":
            # Use simple environment variable database for Railway
            from .env_db import EnvDatabase
            logger.info("Using environment variable database (USE_ENV_DB=true)")
            # Return EnvDatabase wrapped to match DonorsDatabase interface
            class EnvDatabaseWrapper:
                def __init__(self):
                    self.env_db = EnvDatabase()
                    self.db_path = "env://DONORS_DATA"
                
                def add_donation(self, *args, **kwargs):
                    return self.env_db.add_donation(*args, **kwargs)
                
                def is_premium_user(self, user_id: int) -> bool:
                    return self.env_db.is_premium_user(user_id)
                
                def get_donor_info(self, user_id: int):
                    return self.env_db.get_donor_info(user_id)
                
                def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
                    # Filter donations for this user
                    try:
                        user_donations = [
                            d for d in self.env_db.data.get("donations", [])
                            if d["user_id"] == user_id
                        ]
                        return sorted(user_donations, key=lambda x: x["payment_date"], reverse=True)
                    except:
                        return []
                
                def get_stats(self):
                    return self.env_db.get_stats()
                
                def get_user_language(self, user_id: int) -> str:
                    return "ru"  # Default to Russian
                
                def set_user_language(self, user_id: int, language: str) -> bool:
                    return True  # Ignore language settings in env db
                
                def has_language_set(self, user_id: int) -> bool:
                    return False
                
                def reset_user_language(self, user_id: int) -> bool:
                    return True
            
            _donors_db = EnvDatabaseWrapper()
        else:
            # Use SQLite for local development
            _donors_db = DonorsDatabase()
    return _donors_db