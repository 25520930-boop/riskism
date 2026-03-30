"""
Optional Firebase authentication helpers for Riskism.
Keeps the existing local auth flow working when Firebase is not configured.
"""
import json
import os
from functools import lru_cache
from typing import Optional

from backend.config import get_settings

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
except Exception:  # pragma: no cover - optional dependency
    firebase_admin = None
    firebase_auth = None
    credentials = None


FIREBASE_APP_NAME = "riskism-firebase"


def _public_config_dict() -> dict:
    settings = get_settings()
    return {
        "apiKey": settings.firebase_api_key,
        "authDomain": settings.firebase_auth_domain,
        "projectId": settings.firebase_project_id,
        "storageBucket": settings.firebase_storage_bucket,
        "messagingSenderId": settings.firebase_messaging_sender_id,
        "appId": settings.firebase_app_id,
        "measurementId": settings.firebase_measurement_id,
    }


def _load_service_account():
    settings = get_settings()
    if not credentials:
        return None

    if settings.firebase_service_account_path:
        path = settings.firebase_service_account_path
        if os.path.exists(path):
            return credentials.Certificate(path)

    if settings.firebase_service_account_json:
        try:
            return credentials.Certificate(json.loads(settings.firebase_service_account_json))
        except Exception:
            return None

    return None


@lru_cache()
def get_firebase_app():
    if not firebase_admin or not credentials:
        return None

    cred = _load_service_account()
    if not cred:
        return None

    try:
        return firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        pass

    settings = get_settings()
    options = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    try:
        return firebase_admin.initialize_app(
            cred,
            options if options else None,
            name=FIREBASE_APP_NAME,
        )
    except Exception:
        return None


def get_firebase_public_config() -> dict:
    config = _public_config_dict()
    enabled = bool(
        get_firebase_app()
        and config.get("apiKey")
        and config.get("authDomain")
        and config.get("projectId")
        and config.get("appId")
    )
    return {
        "enabled": enabled,
        "config": config if enabled else None,
        "providers": ["google"] if enabled else [],
    }


def verify_firebase_id_token(id_token: str) -> Optional[dict]:
    app = get_firebase_app()
    if not app or not firebase_auth or not id_token:
        return None

    try:
        return firebase_auth.verify_id_token(id_token, app=app, check_revoked=False)
    except Exception:
        return None
