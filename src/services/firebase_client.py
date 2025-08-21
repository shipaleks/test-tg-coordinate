import os
import json
import base64
from typing import Optional

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore

_firestore: Optional[firestore.Client] = None


def get_firestore() -> firestore.Client:
    global _firestore
    if _firestore is not None:
        return _firestore

    json_raw = os.getenv("FIREBASE_CREDENTIALS_JSON")
    b64 = os.getenv("FIREBASE_CREDENTIALS_B64")

    if json_raw:
        info = json.loads(json_raw)
        cred = credentials.Certificate(info)
    elif b64:
        info = json.loads(base64.b64decode(b64).decode("utf-8"))
        cred = credentials.Certificate(info)
    else:
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
        private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
        if not (project_id and client_email and private_key):
            raise RuntimeError("No Firebase credentials provided in environment variables")
        info = {
            "type": "service_account",
            "project_id": project_id,
            "client_email": client_email,
            "private_key": private_key,
        }
        cred = credentials.Certificate(info)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    _firestore = firestore.Client()
    return _firestore


