"""Send push notifications to Android phones through Firebase Cloud Messaging (HTTP v1).

The Pi signs a short-lived token request with the Firebase service-account key and
sends each message to Google; it needs outbound internet only. Without a key file
(``FCM_CREDENTIALS_FILE``) nothing is sent and reminders stay in the app.
"""
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from jose import jwt

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


class PushNotConfigured(RuntimeError):
    pass


class InvalidDeviceToken(RuntimeError):
    """The phone uninstalled the app or the token expired; forget the device."""


@dataclass
class _AccessToken:
    value: str
    expires_at: float


class FcmSender:
    def __init__(self, credentials_file: str | None, timeout_seconds: float = 10.0, client: httpx.Client | None = None):
        if not credentials_file or not Path(credentials_file).is_file():
            raise PushNotConfigured("No Firebase service-account file is configured")
        info = json.loads(Path(credentials_file).read_text(encoding="utf-8"))
        self._project = info["project_id"]
        self._email = info["client_email"]
        self._key = info["private_key"]
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._token: _AccessToken | None = None

    def _access_token(self) -> str:
        if self._token and self._token.expires_at - 60 > time.time():
            return self._token.value
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": self._email, "scope": _SCOPE, "aud": _TOKEN_URL, "iat": now, "exp": now + 3600},
            self._key,
            algorithm="RS256",
        )
        response = self._client.post(_TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion,
        })
        response.raise_for_status()
        body = response.json()
        self._token = _AccessToken(body["access_token"], now + int(body.get("expires_in", 3600)))
        return self._token.value

    def send(self, device_token: str, title: str, body: str, data: dict[str, str] | None = None) -> None:
        message = {
            "message": {
                "token": device_token,
                "notification": {"title": title, "body": body},
                "data": data or {},
                "android": {"priority": "high"},
            }
        }
        response = self._client.post(
            _SEND_URL.format(project=self._project),
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json=message,
        )
        if response.status_code == 404 or (response.status_code == 400 and "UNREGISTERED" in response.text):
            raise InvalidDeviceToken("Device token is no longer valid")
        response.raise_for_status()
