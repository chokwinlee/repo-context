def record_invoice(payload: bytes) -> dict[str, str]:
    return {"stored": str(len(payload))}
