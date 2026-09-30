import hmac
import hashlib
import json
import uuid
import pytest
import pytest_asyncio
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.app.main import app
from backend.app.db.database import engine, Base, AsyncSessionLocal
from backend.app.db.models import Transaction, Account, ReconciliationRecord, WebhookEvent
from backend.app.modules.webhooks.router import PROCESSED_EVENTS


@pytest_asyncio.fixture(autouse=True)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    PROCESSED_EVENTS.clear()
    yield


@pytest.mark.asyncio
async def test_paystack_webhook_charge_success_ledger_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Setup user & business & account
        verify_res = await client.post("/api/v1/auth/verify-otp", json={"phone": "+233541112233", "otp": "123456"})
        access_token = verify_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        biz_res = await client.post(
            "/api/v1/businesses",
            json={"name": "Acme Corp", "base_currency": "GHS"},
            headers=headers,
        )
        business_id_str = biz_res.json()["data"]["id"]
        business_id = uuid.UUID(business_id_str)
        headers["X-Business-ID"] = business_id_str

        acc_res = await client.post(
            "/api/v1/accounts",
            json={"name": "MTN MoMo Business", "type": "MOBILE_MONEY", "currency": "GHS", "opening_balance": "100.00"},
            headers=headers,
        )
        account_id_str = acc_res.json()["data"]["id"]
        account_id = uuid.UUID(account_id_str)

        # 2. Trigger charge.success webhook (amount is 50000 pesewas = 500.00 GHS)
        webhook_payload = {
            "event": "charge.success",
            "data": {
                "id": 9901,
                "reference": "REF_CHARGE_001",
                "amount": 50000,
                "currency": "GHS",
                "channel": "mobile_money",
                "paid_at": "2026-09-28T10:00:00.000Z",
                "metadata": {
                    "business_id": business_id_str,
                    "account_id": account_id_str,
                    "invoice_id": "INV-2026-001",
                },
                "customer": {
                    "email": "customer@example.com",
                    "first_name": "Ama",
                    "last_name": "Mensah",
                },
            },
        }

        res = await client.post("/api/v1/webhooks/paystack", json=webhook_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["data"]["already_processed"] is False

        # 3. Duplicate event should be ignored
        res_dup = await client.post("/api/v1/webhooks/paystack", json=webhook_payload)
        assert res_dup.status_code == 200
        assert res_dup.json()["data"]["already_processed"] is True
        assert res_dup.json()["message"] == "Duplicate event ignored"

        # 4. Verify DB state: Transaction recorded, Balance updated, Reconciliation MATCHED
        async with AsyncSessionLocal() as db:
            # Check transaction
            txs = (await db.execute(select(Transaction).where(Transaction.business_id == business_id))).scalars().all()
            assert len(txs) == 1
            tx = txs[0]
            assert tx.type == "INCOME"
            assert tx.original_amount == Decimal("500.00")
            assert tx.original_currency == "GHS"
            assert tx.sync_metadata.get("reference") == "REF_CHARGE_001"
            assert tx.sync_metadata.get("invoice_id") == "INV-2026-001"

            # Check account balance: 100.00 opening + 500.00 income = 600.00
            acc = await db.get(Account, account_id)
            assert acc.current_balance == Decimal("600.0000")

            # Check reconciliation record
            recs = (await db.execute(select(ReconciliationRecord).where(ReconciliationRecord.business_id == business_id))).scalars().all()
            assert len(recs) == 1
            assert recs[0].status == "MATCHED"
            assert recs[0].external_transaction_id == "REF_CHARGE_001"
            assert recs[0].transaction_id == tx.id


@pytest.mark.asyncio
async def test_paystack_webhook_transfer_success_and_failure_reversal():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Setup
        verify_res = await client.post("/api/v1/auth/verify-otp", json={"phone": "+233541112244", "otp": "123456"})
        access_token = verify_res.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        biz_res = await client.post(
            "/api/v1/businesses",
            json={"name": "Kofi Logistics", "base_currency": "GHS"},
            headers=headers,
        )
        business_id_str = biz_res.json()["data"]["id"]
        business_id = uuid.UUID(business_id_str)
        headers["X-Business-ID"] = business_id_str

        acc_res = await client.post(
            "/api/v1/accounts",
            json={"name": "Operational Bank", "type": "BANK", "currency": "GHS", "opening_balance": "1000.00"},
            headers=headers,
        )
        account_id_str = acc_res.json()["data"]["id"]
        account_id = uuid.UUID(account_id_str)

        # 1. Trigger transfer.success (Payout of 200.00 GHS = 20000 pesewas)
        transfer_payload = {
            "event": "transfer.success",
            "data": {
                "id": 8801,
                "transfer_code": "TRF_001",
                "reference": "REF_TRF_001",
                "amount": 20000,
                "currency": "GHS",
                "reason": "Driver weekly stipend",
                "recipient": {"name": "Kwame Mensah"},
                "metadata": {
                    "business_id": business_id_str,
                    "account_id": account_id_str,
                },
            },
        }

        res = await client.post("/api/v1/webhooks/paystack", json=transfer_payload)
        assert res.status_code == 200

        async with AsyncSessionLocal() as db:
            acc = await db.get(Account, account_id)
            # 1000.00 opening - 200.00 payout = 800.00
            assert acc.current_balance == Decimal("800.0000")

            txs = (await db.execute(select(Transaction).where(Transaction.business_id == business_id))).scalars().all()
            assert len(txs) == 1
            assert txs[0].type == "EXPENSE"
            assert txs[0].original_amount == Decimal("200.00")
            assert txs[0].status == "ACTIVE"

        # 2. Trigger transfer.reversed -> should void the expense and re-credit the 200.00
        reverse_payload = {
            "event": "transfer.reversed",
            "data": {
                "id": 8802,
                "transfer_code": "TRF_001",
                "reference": "REF_TRF_001",
                "amount": 20000,
                "currency": "GHS",
                "reason": "Destination account blocked",
                "metadata": {
                    "business_id": business_id_str,
                    "account_id": account_id_str,
                },
            },
        }

        res_rev = await client.post("/api/v1/webhooks/paystack", json=reverse_payload)
        assert res_rev.status_code == 200

        async with AsyncSessionLocal() as db:
            acc = await db.get(Account, account_id)
            # 800.00 + 200.00 re-credited = 1000.00
            assert acc.current_balance == Decimal("1000.0000")

            txs = (await db.execute(select(Transaction).where(Transaction.business_id == business_id))).scalars().all()
            active_expense = [t for t in txs if t.status == "ACTIVE" and t.type == "EXPENSE"]
            assert len(active_expense) == 0


@pytest.mark.asyncio
async def test_paystack_webhook_hmac_signature_validation(monkeypatch):
    secret_key = "sk_test_secret_paystack_key_12345"
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", secret_key)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        body = json.dumps({"event": "charge.success", "data": {"id": 12345, "amount": 1000}}).encode("utf-8")
        valid_signature = hmac.new(secret_key.encode("utf-8"), body, hashlib.sha512).hexdigest()

        # 1. Without signature -> 401 Unauthorized
        res_no_sig = await client.post(
            "/api/v1/webhooks/paystack",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert res_no_sig.status_code == 401

        # 2. With invalid signature -> 401 Unauthorized
        res_bad_sig = await client.post(
            "/api/v1/webhooks/paystack",
            content=body,
            headers={"Content-Type": "application/json", "x-paystack-signature": "invalid_sig"},
        )
        assert res_bad_sig.status_code == 401

        # 3. With valid signature -> 200 OK
        res_good_sig = await client.post(
            "/api/v1/webhooks/paystack",
            content=body,
            headers={"Content-Type": "application/json", "x-paystack-signature": valid_signature},
        )
        assert res_good_sig.status_code == 200
        assert res_good_sig.json()["status"] == "ok"
