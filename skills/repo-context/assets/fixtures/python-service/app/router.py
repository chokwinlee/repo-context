from fastapi import APIRouter, Request

from app.services.invoice_service import record_invoice
from app.services.payment_gateway import verify_webhook_signature

router = APIRouter()


@router.post("/webhooks/billing")
async def billing_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    verify_webhook_signature(payload)
    record_invoice(payload)
    return {"status": "ok"}
