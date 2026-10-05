"""Firebase Cloud Messaging (HTTP v1) sender for customer app pushes."""

import json
import threading
import time

import requests

from app.core.config import FIREBASE_SERVICE_ACCOUNT_FILE, FIREBASE_SERVICE_ACCOUNT_JSON

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_lock = threading.Lock()
_creds = None
_project_id: str | None = None


class PushNotConfigured(RuntimeError):
    pass


class PushTokenInvalid(RuntimeError):
    """FCM says the token is unregistered / malformed — delete it."""


def _load_info() -> dict:
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        return json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
    if FIREBASE_SERVICE_ACCOUNT_FILE:
        try:
            with open(FIREBASE_SERVICE_ACCOUNT_FILE, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            raise PushNotConfigured(
                f"Firebase key file not found: {FIREBASE_SERVICE_ACCOUNT_FILE}"
            )
    raise PushNotConfigured(
        "Set FIREBASE_SERVICE_ACCOUNT_FILE or FIREBASE_SERVICE_ACCOUNT_JSON."
    )


def _access_token() -> tuple[str, str]:
    global _creds, _project_id
    # Lazy import keeps google-auth transport off the Lambda cold-start path.
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    with _lock:
        if _creds is None:
            info = _load_info()
            _creds = service_account.Credentials.from_service_account_info(
                info, scopes=[_SCOPE]
            )
            _project_id = info["project_id"]
        if not _creds.valid or (_creds.expiry and _creds.expiry.timestamp() - time.time() < 60):
            _creds.refresh(Request())
        return _creds.token, _project_id  # type: ignore[return-value]


def send_to_token(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    image: str | None = None,
) -> str:
    """Send one notification. Returns the FCM message name.

    `image` must be a public https URL (shown as a big picture on Android).
    """
    access_token, project_id = _access_token()
    notification: dict = {"title": title, "body": body}
    if image:
        notification["image"] = image
    message: dict = {
        "token": token,
        "notification": notification,
        "android": {
            "priority": "HIGH",
            "notification": {"channel_id": "renown_default", "sound": "default"},
        },
    }
    payload_data = {k: str(v) for k, v in (data or {}).items()}
    if image:
        payload_data["image"] = image
    if payload_data:
        message["data"] = payload_data

    res = requests.post(
        f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"message": message},
        timeout=15,
    )
    if res.status_code == 200:
        return res.json().get("name", "")
    detail = res.text[:500]
    if res.status_code == 404 or "UNREGISTERED" in detail or "INVALID_ARGUMENT" in detail:
        raise PushTokenInvalid(detail)
    raise RuntimeError(f"FCM {res.status_code}: {detail}")
