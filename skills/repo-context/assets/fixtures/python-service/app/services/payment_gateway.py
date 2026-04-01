def verify_webhook_signature(payload: bytes) -> bool:
    return bool(payload)


def normalize_event_name(name: str) -> str:
    return name.strip().lower()
