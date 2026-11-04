"""Notificaciones push al celular (Web Push), aunque la app esté cerrada."""
import base64
import json
import logging
import threading

from .paths import DATA_DIR

KEY_FILE = DATA_DIR / "vapid_private.pem"
SUBSCRIPTIONS_FILE = DATA_DIR / "push.json"
CLAIMS = {"sub": "mailto:jarvis@example.com"}

log = logging.getLogger("jarvis.push")
_lock = threading.Lock()


def _vapid():
    from py_vapid import Vapid

    if not KEY_FILE.exists():
        vapid = Vapid()
        vapid.generate_keys()
        DATA_DIR.mkdir(exist_ok=True)
        vapid.save_key(str(KEY_FILE))
    return Vapid.from_file(str(KEY_FILE))


def public_key() -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    raw = _vapid().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _subscriptions() -> list[dict]:
    if not SUBSCRIPTIONS_FILE.exists():
        return []
    return json.loads(SUBSCRIPTIONS_FILE.read_text(encoding="utf-8"))


def _save(subscriptions: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SUBSCRIPTIONS_FILE.write_text(json.dumps(subscriptions), encoding="utf-8")


def subscribe(subscription: dict) -> None:
    if not subscription.get("endpoint", "").startswith("https://") or "keys" not in subscription:
        raise ValueError("Suscripción no válida")
    with _lock:
        subscriptions = [item for item in _subscriptions() if item["endpoint"] != subscription["endpoint"]]
        _save(subscriptions + [subscription])


def has_subscribers() -> bool:
    return bool(_subscriptions())


def send(title: str, body: str) -> int:
    """Devuelve a cuántos dispositivos llegó. Las suscripciones caducadas se borran."""
    from pywebpush import WebPushException, webpush

    if not has_subscribers():
        return 0
    key = str(KEY_FILE)
    _vapid()
    sent = 0
    expired = []
    for subscription in _subscriptions():
        try:
            webpush(subscription, json.dumps({"title": title, "body": body}), vapid_private_key=key,
                    vapid_claims=dict(CLAIMS), ttl=3600)
            sent += 1
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in (404, 410):
                expired.append(subscription["endpoint"])
            else:
                log.warning("Push falló: %s", error)
        except Exception:
            log.exception("Push falló")
    if expired:
        with _lock:
            _save([item for item in _subscriptions() if item["endpoint"] not in expired])
    return sent
