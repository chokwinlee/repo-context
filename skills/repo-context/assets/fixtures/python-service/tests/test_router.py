from app.router import billing_webhook


def test_billing_webhook_exists() -> None:
    assert billing_webhook is not None
