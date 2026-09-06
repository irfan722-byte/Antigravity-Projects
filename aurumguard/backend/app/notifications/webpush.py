"""Web Push (VAPID) provider using pywebpush. Requires VAPID keys in the environment."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from ..providers.base import ProviderHealth, PushMessage, PushProvider, PushResult


class WebPushProvider(PushProvider):
    name = "webpush"
    is_mock = False

    def __init__(self, public_key: str, private_key: str, subject: str):
        self.public_key = public_key
        self.private_key = private_key
        self.subject = subject
        self._failures = 0
        self._last_error: str | None = None
        self._last_ok: datetime | None = None

    def send(self, subscription: dict, message: PushMessage) -> PushResult:
        from pywebpush import WebPushException, webpush

        now = datetime.now(tz=UTC)
        payload = json.dumps({"title": message.title, "body": message.body, "data": message.data, "tag": message.tag, "priority": message.priority})
        try:
            webpush(subscription_info=subscription, data=payload, vapid_private_key=self.private_key, vapid_claims={"sub": self.subject}, ttl=3600)
            self._last_ok = now
            self._failures = 0
            return PushResult(True, self.name, "sent", now)
        except WebPushException as exc:  # pragma: no cover - network
            self._failures += 1
            self._last_error = str(exc)
            return PushResult(False, self.name, str(exc), now)

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, self._failures < 5 and bool(self.private_key), False, self._last_ok, self._last_error, None, self._failures)
