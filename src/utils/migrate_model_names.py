"""Migration script to update model names from gpt-5/gpt-5-mini to gpt-5.1/gpt-5.1-mini.

This script updates all existing users who have old model names in the database.
Run this once after deploying the GPT-5.1 update.

Usage:
    python -m src.utils.migrate_model_names
"""

import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_model_names():
    """Migrate all users from old model names to new ones."""
    from src.services.async_donors_wrapper import get_async_donors_db
    
    db = await get_async_donors_db()
    
    # Check which database backend we're using
    if hasattr(db, '_is_postgres') and db._is_postgres:
        logger.info("Migrating PostgreSQL database...")
        await migrate_postgres(db._db)
    elif hasattr(db, '_use_firestore') and db._use_firestore:
        logger.info("Migrating Firestore database...")
        await migrate_firestore(db._db)
    else:
        logger.info("Migrating SQLite database...")
        await migrate_sqlite(db._db)
    
    logger.info("Migration complete!")


async def migrate_postgres(pg_db):
    """Migrate PostgreSQL database."""
    try:
        async with pg_db.pool.acquire() as conn:
            # Update gpt-5-mini → gpt-5.1-mini
            result1 = await conn.execute(
                "UPDATE user_preferences SET model = 'gpt-5.1-mini' WHERE model = 'gpt-5-mini'"
            )
            logger.info(f"Updated gpt-5-mini → gpt-5.1-mini: {result1}")
            
            # Update gpt-5 → gpt-5.1
            result2 = await conn.execute(
                "UPDATE user_preferences SET model = 'gpt-5.1' WHERE model = 'gpt-5'"
            )
            logger.info(f"Updated gpt-5 → gpt-5.1: {result2}")
            
            # Count users with each model
            counts = await conn.fetch(
                "SELECT model, COUNT(*) as count FROM user_preferences GROUP BY model"
            )
            logger.info("Current model distribution:")
            for row in counts:
                logger.info(f"  {row['model']}: {row['count']} users")
                
    except Exception as e:
        logger.error(f"PostgreSQL migration failed: {e}")
        raise


async def migrate_firestore(fs_db):
    """Migrate Firestore database."""
    try:
        db = fs_db.db
        users = db.collection("users").stream()
        
        updated_count = 0
        for doc in users:
            data = doc.to_dict() or {}
            model = data.get("model")
            
            new_model = None
            if model == "gpt-5-mini":
                new_model = "gpt-5.1-mini"
            elif model == "gpt-5":
                new_model = "gpt-5.1"
            
            if new_model:
                doc.reference.update({"model": new_model})
                updated_count += 1
                logger.info(f"Updated user {doc.id}: {model} → {new_model}")
        
        logger.info(f"Total users updated: {updated_count}")
        
    except Exception as e:
        logger.error(f"Firestore migration failed: {e}")
        raise


async def migrate_sqlite(sqlite_db):
    """Migrate SQLite database."""
    try:
        import sqlite3
        
        with sqlite3.connect(sqlite_db.db_path) as conn:
            # Update gpt-5-mini → gpt-5.1-mini
            cursor1 = conn.execute(
                "UPDATE user_preferences SET model = 'gpt-5.1-mini' WHERE model = 'gpt-5-mini'"
            )
            logger.info(f"Updated gpt-5-mini → gpt-5.1-mini: {cursor1.rowcount} rows")
            
            # Update gpt-5 → gpt-5.1
            cursor2 = conn.execute(
                "UPDATE user_preferences SET model = 'gpt-5.1' WHERE model = 'gpt-5'"
            )
            logger.info(f"Updated gpt-5 → gpt-5.1: {cursor2.rowcount} rows")
            
            conn.commit()
            
            # Count users with each model
            rows = conn.execute(
                "SELECT model, COUNT(*) as count FROM user_preferences GROUP BY model"
            ).fetchall()
            
            logger.info("Current model distribution:")
            for model, count in rows:
                logger.info(f"  {model}: {count} users")
                
    except Exception as e:
        logger.error(f"SQLite migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(migrate_model_names())

