"""Environment variable based database for Railway deployment."""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class EnvDatabase:
    """Simple database using environment variables for Railway."""

    def __init__(self):
        """Initialize the environment database."""
        self.env_key = "DONORS_DATA"
        self._load_data()

    def _load_data(self):
        """Load data from environment variable."""
        try:
            raw_data = os.environ.get(self.env_key, "{}")
            self.data = json.loads(raw_data)
            if "donors" not in self.data:
                self.data["donors"] = {}
            if "donations" not in self.data:
                self.data["donations"] = []
            logger.info(f"Loaded {len(self.data['donors'])} donors from environment")
        except Exception as e:
            logger.error(f"Failed to load data from environment: {e}")
            self.data = {"donors": {}, "donations": []}

    def _save_data(self):
        """Save data to environment variable (manual update needed)."""
        try:
            json_data = json.dumps(self.data, separators=(",", ":"))
            logger.info(f"UPDATE RAILWAY ENV: {self.env_key}={json_data}")
            # Note: Can't actually update env vars at runtime
            # User needs to manually update in Railway dashboard
            return json_data
        except Exception as e:
            logger.error(f"Failed to serialize data: {e}")
            return None

    def add_donation(
        self,
        user_id: int,
        payment_id: str,
        stars_amount: int,
        telegram_username: str | None = None,
        first_name: str | None = None,
        invoice_payload: str | None = None,
    ) -> bool:
        """Add a new donation."""
        try:
            current_time = int(time.time())

            # Check if payment already exists
            for donation in self.data["donations"]:
                if donation["payment_id"] == payment_id:
                    logger.warning(f"Payment {payment_id} already exists")
                    return False

            # Add donation
            self.data["donations"].append(
                {
                    "user_id": user_id,
                    "payment_id": payment_id,
                    "stars_amount": stars_amount,
                    "payment_date": current_time,
                    "invoice_payload": invoice_payload,
                }
            )

            # Update or create donor
            user_key = str(user_id)
            if user_key in self.data["donors"]:
                donor = self.data["donors"][user_key]
                donor["total_stars"] += stars_amount
                donor["last_donation_date"] = current_time
            else:
                self.data["donors"][user_key] = {
                    "user_id": user_id,
                    "telegram_username": telegram_username,
                    "first_name": first_name,
                    "total_stars": stars_amount,
                    "first_donation_date": current_time,
                    "last_donation_date": current_time,
                    "premium_expires": current_time
                    + (25 * 365 * 24 * 60 * 60),  # 25 years
                }

            # Log the update command for manual update
            new_data = self._save_data()
            if new_data:
                logger.info("MANUAL UPDATE REQUIRED in Railway Variables:")
                logger.info(f"{self.env_key}={new_data[:100]}...")

            return True
        except Exception as e:
            logger.error(f"Failed to add donation: {e}")
            return False

    def is_premium_user(self, user_id: int) -> bool:
        """Check if user has premium status."""
        try:
            user_key = str(user_id)
            if user_key in self.data["donors"]:
                donor = self.data["donors"][user_key]
                return donor.get("premium_expires", 0) > int(time.time())
            return False
        except Exception as e:
            logger.error(f"Failed to check premium status: {e}")
            return False

    def get_donor_info(self, user_id: int) -> dict[str, Any] | None:
        """Get donor information."""
        try:
            user_key = str(user_id)
            if user_key in self.data["donors"]:
                return self.data["donors"][user_key].copy()
            return None
        except Exception as e:
            logger.error(f"Failed to get donor info: {e}")
            return None

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        try:
            total_donors = len(self.data["donors"])
            total_donations = len(self.data["donations"])
            total_stars = sum(d["stars_amount"] for d in self.data["donations"])
            active_premium = sum(
                1
                for d in self.data["donors"].values()
                if d.get("premium_expires", 0) > int(time.time())
            )

            return {
                "total_donors": total_donors,
                "total_donations": total_donations,
                "total_stars": total_stars,
                "active_premium": active_premium,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
