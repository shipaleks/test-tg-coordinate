from datetime import datetime
from typing import Optional
import logging

from google.cloud.firestore import Client
from google.cloud import firestore

from .firebase_client import get_firestore


USERS_COLLECTION = "users"
METRICS_DOC_PATH = ("metrics", "counters")


def _server_timestamp():
    return firestore.SERVER_TIMESTAMP


async def ensure_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    try:
        db: Client = get_firestore()
        user_ref = db.collection(USERS_COLLECTION).document(str(user_id))
        metrics_ref = db.collection(METRICS_DOC_PATH[0]).document(METRICS_DOC_PATH[1])

        @firestore.transactional
        def _tx(transaction):
            user_snapshot = user_ref.get(transaction=transaction)
            metrics_snapshot = metrics_ref.get(transaction=transaction)

            if not user_snapshot.exists:
                # Create metrics if not exists
                if not metrics_snapshot.exists:
                    transaction.set(metrics_ref, {
                        "total_users": 0,
                        "total_facts": 0,
                    })

                transaction.set(user_ref, {
                    "username": username,
                    "first_name": first_name,
                    "facts_count": 0,
                    "created_at": _server_timestamp(),
                    "last_seen_at": _server_timestamp(),
                })
                transaction.update(metrics_ref, {"total_users": firestore.Increment(1)})
            else:
                transaction.update(user_ref, {"last_seen_at": _server_timestamp()})

        _tx(db.transaction())
    except Exception as e:
        logging.getLogger(__name__).warning(f"ensure_user skipped (firebase not configured or error): {e}")


async def increment_fact_counters(user_id: int, delta: int = 1) -> None:
    try:
        db: Client = get_firestore()
        user_ref = db.collection(USERS_COLLECTION).document(str(user_id))
        metrics_ref = db.collection(METRICS_DOC_PATH[0]).document(METRICS_DOC_PATH[1])

        batch = db.batch()
        batch.update(user_ref, {"facts_count": firestore.Increment(delta)})
        batch.update(metrics_ref, {"total_facts": firestore.Increment(delta)})
        batch.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"increment_fact_counters skipped: {e}")


async def record_movement(user_id: int, lat: float, lon: float, ts: Optional[datetime] = None, session_id: Optional[str] = None) -> None:
    try:
        db: Client = get_firestore()
        coll = db.collection(USERS_COLLECTION).document(str(user_id)).collection("movements")
        data = {
            "lat": lat,
            "lon": lon,
            "ts": _server_timestamp() if ts is None else ts,
        }
        if session_id:
            data["session_id"] = session_id
        coll.add(data)
    except Exception as e:
        logging.getLogger(__name__).warning(f"record_movement skipped: {e}")


async def get_stats_for_user(user_id: int) -> int:
    try:
        db: Client = get_firestore()
        snap = db.collection(USERS_COLLECTION).document(str(user_id)).get()
        if snap.exists:
            return int(snap.get("facts_count") or 0)
    except Exception as e:
        logging.getLogger(__name__).warning(f"get_stats_for_user fallback to 0: {e}")
    return 0


async def get_global_stats() -> dict:
    try:
        db: Client = get_firestore()
        snap = db.collection(METRICS_DOC_PATH[0]).document(METRICS_DOC_PATH[1]).get()
        if not snap.exists:
            return {"total_users": 0, "total_facts": 0}
        return {
            "total_users": int(snap.get("total_users") or 0),
            "total_facts": int(snap.get("total_facts") or 0),
        }
    except Exception as e:
        logging.getLogger(__name__).warning(f"get_global_stats fallback to zeros: {e}")
        return {"total_users": 0, "total_facts": 0}


