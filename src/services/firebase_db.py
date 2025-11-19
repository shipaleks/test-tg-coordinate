"""Firestore-backed persistent storage for donors and user preferences.

This adapter mirrors the interface used by AsyncDonorsWrapper so we can
switch persistence from SQLite/Postgres to Firestore via environment flag
without touching the rest of the code.
"""

from __future__ import annotations

import time
import logging
from typing import Optional, List, Dict, Any

from .firebase_client import get_firestore


logger = logging.getLogger(__name__)


class FirestoreDatabase:
    """Minimal Firestore persistence.

    Collections:
    - users/{user_id}: { username?, first_name?, facts_count, premium_expires?, language?, reasoning?, model? }
    - donations/{payment_id}: { user_id, stars_amount, payment_date, invoice_payload }
    - metrics/counters: { total_users, total_facts } (already maintained elsewhere)
    """

    def __init__(self) -> None:
        self.db = get_firestore()
        self.db_path = "firestore://users,donations"
        # Expose a convenience for bulk reset (best-effort, optional)
        self.reset_all_languages = self._reset_all_languages

    # ----- Donations / Donors -----
    def add_donation(
        self,
        user_id: int,
        payment_id: str,
        stars_amount: int,
        telegram_username: Optional[str] = None,
        first_name: Optional[str] = None,
        invoice_payload: Optional[str] = None,
    ) -> bool:
        try:
            now = int(time.time())
            users = self.db.collection("users")
            user_ref = users.document(str(user_id))
            donations = self.db.collection("donations")
            donation_ref = donations.document(payment_id)

            # Idempotency: if donation exists, no-op
            if donation_ref.get().exists:
                logger.warning(f"Donation {payment_id} already exists")
                return False

            batch = self.db.batch()
            # Create donor doc if not exists and update totals/premium
            user_snapshot = user_ref.get()
            if user_snapshot.exists:
                data = user_snapshot.to_dict() or {}
                total = int(data.get("total_stars", 0)) + int(stars_amount)
                update = {
                    "total_stars": total,
                    "last_donation_date": now,
                    "telegram_username": telegram_username,
                    "first_name": first_name,
                    # 25 лет премиума, как и в SQLite/Postgres варианте
                    "premium_expires": now + 25 * 365 * 24 * 60 * 60,
                }
                batch.update(user_ref, update)
            else:
                batch.set(
                    user_ref,
                    {
                        "telegram_username": telegram_username,
                        "first_name": first_name,
                        "facts_count": 0,
                        "total_stars": int(stars_amount),
                        "first_donation_date": now,
                        "last_donation_date": now,
                        "premium_expires": now + 25 * 365 * 24 * 60 * 60,
                    },
                )

            batch.set(
                donation_ref,
                {
                    "user_id": int(user_id),
                    "payment_id": payment_id,
                    "stars_amount": int(stars_amount),
                    "payment_date": now,
                    "invoice_payload": invoice_payload,
                },
            )

            batch.commit()
            logger.info(
                f"Added donation to Firestore: user_id={user_id}, stars={stars_amount}, payment_id={payment_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Firestore add_donation failed: {e}")
            return False

    def is_premium_user(self, user_id: int) -> bool:
        try:
            now = int(time.time())
            snap = self.db.collection("users").document(str(user_id)).get()
            if not snap.exists:
                return False
            exp = int(snap.to_dict().get("premium_expires", 0) or 0)
            return exp > now
        except Exception as e:
            logger.error(f"Firestore is_premium_user failed: {e}")
            return False

    def get_donor_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            snap = self.db.collection("users").document(str(user_id)).get()
            return snap.to_dict() if snap.exists else None
        except Exception as e:
            logger.error(f"Firestore get_donor_info failed: {e}")
            return None

    def get_donation_history(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            q = (
                self.db.collection("donations")
                .where("user_id", "==", int(user_id))
                .order_by("payment_date", direction="DESCENDING")
                .limit(100)
            )
            docs = q.stream()
            return [d.to_dict() for d in docs]
        except Exception as e:
            logger.error(f"Firestore get_donation_history failed: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            # Best-effort light stats
            total_donations = (
                len(list(self.db.collection("donations").limit(1_000).stream()))
            )
            total_donors = len(list(self.db.collection("users").where("total_stars", ">", 0).limit(1_000).stream()))
            return {
                "total_donors": total_donors,
                "total_donations": total_donations,
                # stars sum could be added later if needed
                "total_stars": 0,
                "active_premium": 0,
                "users_with_language": 0,
            }
        except Exception:
            return {}

    # ----- User preferences -----
    def get_user_language(self, user_id: int) -> str:
        try:
            snap = self.db.collection("users").document(str(user_id)).get()
            if snap.exists:
                lang = (snap.to_dict() or {}).get("language")
                return lang or "ru"
        except Exception:
            pass
        return "ru"

    def set_user_language(self, user_id: int, language: str) -> bool:
        try:
            ref = self.db.collection("users").document(str(user_id))
            ref.set({"language": language, "updated_at": time.time()}, merge=True)
            return True
        except Exception as e:
            logger.error(f"Firestore set_user_language failed: {e}")
            return False

    def has_language_set(self, user_id: int) -> bool:
        try:
            snap = self.db.collection("users").document(str(user_id)).get()
            if not snap.exists:
                logger.info(f"has_language_set: user {user_id} document does not exist")
                return False
            
            user_data = snap.to_dict() or {}
            has_lang = user_data.get("language") is not None
            logger.info(f"has_language_set: user {user_id} has language={user_data.get('language')}, result={has_lang}")
            return has_lang
        except Exception as e:
            logger.error(f"has_language_set error for user {user_id}: {e}")
            return False

    def reset_user_language(self, user_id: int) -> bool:
        try:
            ref = self.db.collection("users").document(str(user_id))
            ref.set({"language": None, "updated_at": time.time()}, merge=True)
            return True
        except Exception as e:
            logger.error(f"Firestore reset_user_language failed: {e}")
            return False

    def get_user_reasoning(self, user_id: int) -> str:
        try:
            snap = self.db.collection("users").document(str(user_id)).get()
            if snap.exists:
                val = (snap.to_dict() or {}).get("reasoning")
                return (val or "medium").strip()
        except Exception:
            pass
        return "medium"

    def set_user_reasoning(self, user_id: int, level: str) -> bool:
        try:
            ref = self.db.collection("users").document(str(user_id))
            ref.set({"reasoning": level, "updated_at": time.time()}, merge=True)
            return True
        except Exception as e:
            logger.error(f"Firestore set_user_reasoning failed: {e}")
            return False

    def get_user_model(self, user_id: int) -> str:
        try:
            snap = self.db.collection("users").document(str(user_id)).get()
            if snap.exists:
                val = (snap.to_dict() or {}).get("model")
                return (val or "gpt-5.1-mini").strip()
        except Exception:
            pass
        return "gpt-5.1-mini"

    def set_user_model(self, user_id: int, model: str) -> bool:
        try:
            ref = self.db.collection("users").document(str(user_id))
            ref.set({"model": model, "updated_at": time.time()}, merge=True)
            return True
        except Exception as e:
            logger.error(f"Firestore set_user_model failed: {e}")
            return False

    # ----- Maintenance helpers -----
    def _reset_all_languages(self) -> None:
        try:
            # Best-effort: iterate limited batch
            users = self.db.collection("users").limit(2000).stream()
            batch = self.db.batch()
            count = 0
            for doc in users:
                batch.update(doc.reference, {"language": None})
                count += 1
                if count % 400 == 0:
                    batch.commit()
                    batch = self.db.batch()
            batch.commit()
            logger.info(f"Reset language for ~{count} users in Firestore")
        except Exception as e:
            logger.warning(f"Bulk language reset failed: {e}")


