"""Migration script from SQLite to PostgreSQL."""

import asyncio
import sqlite3
import logging
import os
from pathlib import Path

from src.services.postgres_db import PostgresDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_from_sqlite(sqlite_path: str, postgres_db: PostgresDatabase):
    """Migrate data from SQLite to PostgreSQL."""
    
    if not os.path.exists(sqlite_path):
        logger.info(f"SQLite database not found at {sqlite_path}, skipping migration")
        return
    
    logger.info(f"Starting migration from {sqlite_path}")
    
    try:
        # Connect to SQLite
        with sqlite3.connect(sqlite_path) as sqlite_conn:
            sqlite_conn.row_factory = sqlite3.Row
            
            # Migrate donors
            donors = sqlite_conn.execute("SELECT * FROM donors").fetchall()
            logger.info(f"Found {len(donors)} donors to migrate")
            
            for donor in donors:
                async with postgres_db.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO donors 
                        (user_id, telegram_username, first_name, total_stars, 
                         first_donation_date, last_donation_date, premium_expires)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (user_id) DO UPDATE SET
                            total_stars = EXCLUDED.total_stars,
                            last_donation_date = EXCLUDED.last_donation_date,
                            premium_expires = EXCLUDED.premium_expires
                    """, donor['user_id'], donor['telegram_username'], 
                        donor['first_name'], donor['total_stars'],
                        donor['first_donation_date'], donor['last_donation_date'],
                        donor['premium_expires'])
            
            # Migrate donations
            donations = sqlite_conn.execute("SELECT * FROM donations").fetchall()
            logger.info(f"Found {len(donations)} donations to migrate")
            
            for donation in donations:
                async with postgres_db.pool.acquire() as conn:
                    try:
                        await conn.execute("""
                            INSERT INTO donations 
                            (user_id, payment_id, stars_amount, payment_date, invoice_payload)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (payment_id) DO NOTHING
                        """, donation['user_id'], donation['payment_id'], 
                            donation['stars_amount'], donation['payment_date'],
                            donation['invoice_payload'])
                    except Exception as e:
                        logger.warning(f"Skipping duplicate donation {donation['payment_id']}: {e}")
            
            # Migrate user preferences
            try:
                preferences = sqlite_conn.execute("SELECT * FROM user_preferences").fetchall()
                logger.info(f"Found {len(preferences)} user preferences to migrate")
                
                for pref in preferences:
                    async with postgres_db.pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO user_preferences (user_id, language)
                            VALUES ($1, $2)
                            ON CONFLICT (user_id) DO UPDATE SET language = EXCLUDED.language
                        """, pref['user_id'], pref['language'])
            except sqlite3.OperationalError:
                logger.info("No user_preferences table found in SQLite")
        
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


async def check_and_migrate():
    """Check for existing SQLite database and migrate if needed."""
    # Possible SQLite locations
    sqlite_paths = [
        "donors.db",
        "/tmp/railway_data/donors.db",
        "/app/railway_data/donors.db",
        "/data/donors.db",
        "/data/appdata/donors.db"
    ]
    
    # Initialize PostgreSQL
    postgres_db = PostgresDatabase()
    await postgres_db.init()
    
    try:
        # Check if we already have data in PostgreSQL
        async with postgres_db.pool.acquire() as conn:
            donor_count = await conn.fetchval("SELECT COUNT(*) FROM donors")
            
            if donor_count > 0:
                logger.info(f"PostgreSQL already has {donor_count} donors, skipping migration")
                return
        
        # Try to find and migrate from SQLite
        for path in sqlite_paths:
            if os.path.exists(path):
                logger.info(f"Found SQLite database at {path}")
                await migrate_from_sqlite(path, postgres_db)
                break
        else:
            logger.info("No SQLite database found to migrate")
            
    finally:
        await postgres_db.close()


if __name__ == "__main__":
    asyncio.run(check_and_migrate())