import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.db.database import engine, Base


@pytest_asyncio.fixture(autouse=True)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_full_ledger_workflow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Auth & Token
        verify_res = await client.post("/api/v1/auth/verify-otp", json={"phone": "+233540001122", "otp": "123456"})
        assert verify_res.status_code == 200
        tokens = verify_res.json()["data"]
        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Create Business
        biz_res = await client.post(
            "/api/v1/businesses",
            json={"name": "Kofi Tech Solutions", "base_currency": "USD"},
            headers=headers,
        )
        assert biz_res.status_code == 201
        business_id = biz_res.json()["data"]["id"]
        headers["X-Business-ID"] = business_id

        # 3. Create Accounts
        bank_acc = (await client.post(
            "/api/v1/accounts",
            json={"name": "Standard Chartered Bank", "type": "BANK", "currency": "USD", "opening_balance": "5000.00"},
            headers=headers,
        )).json()["data"]

        momo_acc = (await client.post(
            "/api/v1/accounts",
            json={"name": "MTN Mobile Money", "type": "MOBILE_MONEY", "currency": "GHS", "opening_balance": "2000.00"},
            headers=headers,
        )).json()["data"]

        # 4. List Categories
        categories = (await client.get("/api/v1/categories", headers=headers)).json()["data"]
        income_cat = [c for c in categories if c["type"] == "INCOME"][0]
        expense_cat = [c for c in categories if c["type"] == "EXPENSE"][0]

        # 5. Record Multiple Transactions
        tx1 = (await client.post(
            "/api/v1/transactions",
            json={
                "account_id": bank_acc["id"],
                "category_id": income_cat["id"],
                "type": "INCOME",
                "original_amount": "2500.00",
                "original_currency": "USD",
                "description": "Enterprise Retainer Payment",
            },
            headers=headers,
        )).json()["data"]

        tx2 = (await client.post(
            "/api/v1/transactions",
            json={
                "account_id": momo_acc["id"],
                "category_id": expense_cat["id"],
                "type": "EXPENSE",
                "original_amount": "150.00",
                "original_currency": "GHS",
                "description": "Internet Wi-Fi router renewal",
            },
            headers=headers,
        )).json()["data"]

        # 6. Analytics & Anomalies
        anomalies = (await client.get("/api/v1/analytics/anomalies", headers=headers)).json()["data"]
        assert "anomalies_found" in anomalies

        forecast = (await client.get("/api/v1/analytics/forecast?days_ahead=30", headers=headers)).json()["data"]
        assert "forecast_available" in forecast

        # 7. Reconciliation Match
        rec_match = await client.post(
            "/api/v1/reconciliation/match",
            json={
                "provider": "paystack",
                "external_transaction_id": "PSTK_99882233",
                "amount": "2500.00",
                "currency": "USD",
                "transaction_timestamp": tx1["transaction_timestamp"],
                "direction": "INCOME",
                "account_id": bank_acc["id"],
            },
            headers=headers,
        )
        assert rec_match.status_code == 201
        assert rec_match.json()["data"]["status"] == "MATCHED"

        # 8. Webhook Ingestion (Idempotent)
        webhook_res = await client.post(
            "/api/v1/webhooks/paystack",
            json={"id": "evt_10001", "event": "charge.success", "data": {"reference": "REF99001"}},
            headers={"X-Event-ID": "evt_10001"},
        )
        assert webhook_res.status_code == 200
        assert webhook_res.json()["data"]["already_processed"] is False

        # Repeat webhook -> should be idempotent
        webhook_res2 = await client.post(
            "/api/v1/webhooks/paystack",
            json={"id": "evt_10001", "event": "charge.success", "data": {"reference": "REF99001"}},
            headers={"X-Event-ID": "evt_10001"},
        )
        assert webhook_res2.status_code == 200
        assert webhook_res2.json()["data"]["already_processed"] is True

        # 9. Audit Logs
        audit_res = await client.get("/api/v1/audit-logs", headers=headers)
        assert audit_res.status_code == 200
        assert len(audit_res.json()["data"]) > 0
