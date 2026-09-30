import hashlib
import hmac
import json
import logging
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, BackgroundTasks, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.database import get_db, AsyncSessionLocal
from backend.app.db.models import (
    WebhookEvent,
    Business,
    BusinessMembership,
    Account,
    Category,
    Transaction,
    User,
    ReconciliationRecord,
)
from backend.app.services.webhook_service import WebhookService
from backend.app.services.balance_service import BalanceService
from backend.app.services.fx_service import FXService
from backend.app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Official Paystack Webhook IPs (verify with latest docs if needed)
PAYSTACK_IPS = {"52.31.139.75", "52.49.173.169", "52.214.14.220"}

# In-memory / cache / DB set for idempotency
PROCESSED_EVENTS: set = set()


async def _resolve_business(db: AsyncSession, metadata: Dict[str, Any]) -> Optional[Business]:
    if metadata.get("business_id"):
        try:
            biz_id = uuid.UUID(str(metadata["business_id"]))
            biz = (await db.execute(select(Business).where(Business.id == biz_id))).scalar_one_or_none()
            if biz:
                return biz
        except Exception:
            pass

    if metadata.get("account_id"):
        try:
            acc_id = uuid.UUID(str(metadata["account_id"]))
            acc = (await db.execute(select(Account).where(Account.id == acc_id))).scalar_one_or_none()
            if acc:
                biz = (await db.execute(select(Business).where(Business.id == acc.business_id))).scalar_one_or_none()
                if biz:
                    return biz
        except Exception:
            pass

    # Default to first available business
    biz = (await db.execute(select(Business))).scalars().first()
    return biz


async def _resolve_account(
    db: AsyncSession, business: Business, metadata: Dict[str, Any], currency: str
) -> Account:
    if metadata.get("account_id"):
        try:
            acc_id = uuid.UUID(str(metadata["account_id"]))
            acc = (
                await db.execute(
                    select(Account).where(Account.id == acc_id, Account.business_id == business.id)
                )
            ).scalar_one_or_none()
            if acc:
                return acc
        except Exception:
            pass

    # Search for an active account matching currency
    acc = (
        await db.execute(
            select(Account).where(
                Account.business_id == business.id,
                Account.currency == currency.upper(),
                Account.is_archived == False,
            )
        )
    ).scalars().first()
    if acc:
        return acc

    # Search for any active account for this business
    acc = (
        await db.execute(
            select(Account).where(
                Account.business_id == business.id,
                Account.is_archived == False,
            )
        )
    ).scalars().first()
    if acc:
        return acc

    # Create default Paystack account
    new_acc = Account(
        id=uuid.uuid4(),
        business_id=business.id,
        name=f"Paystack Account ({currency.upper()})",
        type="BANK",
        currency=currency.upper(),
        opening_balance=Decimal("0.0000"),
        current_balance=Decimal("0.0000"),
    )
    db.add(new_acc)
    await db.flush()
    return new_acc


async def _resolve_category(
    db: AsyncSession, business: Business, metadata: Dict[str, Any], cat_type: str
) -> Category:
    if metadata.get("category_id"):
        try:
            cat_id = uuid.UUID(str(metadata["category_id"]))
            cat = (await db.execute(select(Category).where(Category.id == cat_id))).scalar_one_or_none()
            if cat:
                return cat
        except Exception:
            pass

    cat = (
        await db.execute(
            select(Category).where(
                (Category.business_id == business.id) | (Category.business_id == None),
                Category.type == cat_type.upper(),
            )
        )
    ).scalars().first()
    if cat:
        return cat

    cat_name = "Sales Income" if cat_type.upper() == "INCOME" else "Payout Expense"
    new_cat = Category(
        id=uuid.uuid4(),
        business_id=business.id,
        name=cat_name,
        type=cat_type.upper(),
        is_default=True,
    )
    db.add(new_cat)
    await db.flush()
    return new_cat


async def _resolve_user_id(
    db: AsyncSession, business: Business, metadata: Dict[str, Any]
) -> uuid.UUID:
    if metadata.get("user_id"):
        try:
            return uuid.UUID(str(metadata["user_id"]))
        except Exception:
            pass
    if metadata.get("created_by_user_id"):
        try:
            return uuid.UUID(str(metadata["created_by_user_id"]))
        except Exception:
            pass

    membership = (
        await db.execute(
            select(BusinessMembership).where(BusinessMembership.business_id == business.id)
        )
    ).scalars().first()
    if membership:
        return membership.user_id

    user = (await db.execute(select(User))).scalars().first()
    if user:
        return user.id

    sys_user = User(
        id=uuid.uuid4(),
        phone="+000000000000",
        name="System Webhook Automation",
        is_active=True,
    )
    db.add(sys_user)
    await db.flush()
    return sys_user.id


async def process_event_background(event_data: dict):
    event_type = event_data.get("event")
    data = event_data.get("data") if isinstance(event_data.get("data"), dict) else {}

    event_id = (
        data.get("id")
        or data.get("reference")
        or event_data.get("id")
        or event_data.get("event_id")
    )
    event_id_str = str(event_id) if event_id else None

    async with AsyncSessionLocal() as db:
        webhook_record = None
        try:
            # 1. Retrieve or record WebhookEvent in DB for auditing & persistent idempotency
            if event_id_str:
                stmt = select(WebhookEvent).where(
                    WebhookEvent.provider == "paystack",
                    WebhookEvent.provider_event_id == event_id_str,
                )
                webhook_record = (await db.execute(stmt)).scalar_one_or_none()
                if webhook_record and webhook_record.status == "PROCESSED":
                    return  # already processed

                if not webhook_record:
                    webhook_record = WebhookEvent(
                        id=uuid.uuid4(),
                        provider="paystack",
                        provider_event_id=event_id_str,
                        event_type=str(event_type or "unknown"),
                        payload=event_data,
                        status="PENDING",
                    )
                    db.add(webhook_record)
                    await db.flush()

            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

            if event_type == "charge.success":
                # 1. Extract payment details: amount (in kobo/pesewas / 100), currency, customer, reference
                amount = Decimal(str(data.get("amount", 0))) / Decimal("100")
                currency = str(data.get("currency") or "GHS").upper()
                reference = str(data.get("reference") or event_id_str or uuid.uuid4())
                customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
                customer_desc = (
                    customer.get("email")
                    or customer.get("phone")
                    or f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
                    or "Paystack Customer"
                )
                invoice_id = metadata.get("invoice_id")

                # Resolve Business, Account, Category, User
                business = await _resolve_business(db, metadata)
                if not business:
                    logger.warning("No business found for Paystack charge.success webhook")
                    return

                account = await _resolve_account(db, business, metadata, currency)
                category = await _resolve_category(db, business, metadata, "INCOME")
                user_id = await _resolve_user_id(db, business, metadata)

                # Check if a transaction already exists for this reference
                stmt_tx = select(Transaction).where(Transaction.business_id == business.id)
                all_txs = (await db.execute(stmt_tx)).scalars().all()
                existing_tx = None
                for t in all_txs:
                    meta = t.sync_metadata or {}
                    if meta.get("reference") == reference or reference in t.description:
                        existing_tx = t
                        break

                if existing_tx:
                    # Update reconciliation record to MATCHED
                    rec_stmt = select(ReconciliationRecord).where(
                        ReconciliationRecord.transaction_id == existing_tx.id
                    )
                    rec = (await db.execute(rec_stmt)).scalars().first()
                    if not rec:
                        rec = ReconciliationRecord(
                            id=uuid.uuid4(),
                            business_id=business.id,
                            transaction_id=existing_tx.id,
                            external_transaction_id=reference,
                            provider="paystack",
                            status="MATCHED",
                        )
                        db.add(rec)
                    else:
                        rec.status = "MATCHED"
                else:
                    # 2. Record income transaction in the ledger
                    rate, fx_snapshot = await FXService.get_or_create_rate_snapshot(
                        db=db,
                        base_currency=business.base_currency,
                        original_currency=currency,
                    )
                    base_amount = FXService.calculate_base_amount(amount, rate)

                    tx = Transaction(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        account_id=account.id,
                        category_id=category.id,
                        created_by_user_id=user_id,
                        type="INCOME",
                        original_amount=amount,
                        original_currency=currency,
                        base_currency_amount=base_amount,
                        exchange_rate_snapshot_id=fx_snapshot.id if fx_snapshot else None,
                        transaction_timestamp=datetime.now(timezone.utc),
                        description=f"Paystack payment ref: {reference} from {customer_desc}",
                        status="ACTIVE",
                        sync_metadata={
                            "provider": "paystack",
                            "reference": reference,
                            "channel": data.get("channel"),
                            "paid_at": data.get("paid_at"),
                            "customer": customer,
                            "event": "charge.success",
                            "invoice_id": invoice_id,
                        },
                    )
                    db.add(tx)
                    if fx_snapshot:
                        fx_snapshot.transaction_id = tx.id

                    await BalanceService.update_balance_on_create(db, account, tx)

                    # 3. Update internal invoice / ledger status & reconciliation
                    rec = ReconciliationRecord(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        transaction_id=tx.id,
                        external_transaction_id=reference,
                        provider="paystack",
                        status="MATCHED",
                    )
                    db.add(rec)

                    await AuditService.log_action(
                        db=db,
                        business_id=business.id,
                        actor_user_id=user_id,
                        entity_type="Transaction",
                        entity_id=tx.id,
                        action="CREATE",
                        before_values=None,
                        after_values={
                            "type": "INCOME",
                            "amount": str(amount),
                            "currency": currency,
                            "reference": reference,
                            "invoice_id": invoice_id,
                            "status": "PAID" if invoice_id else "RECORDED",
                        },
                    )

            elif event_type == "transfer.success":
                # Handle successful payout / transfer
                amount = Decimal(str(data.get("amount", 0))) / Decimal("100")
                currency = str(data.get("currency") or "GHS").upper()
                reference = str(data.get("reference") or data.get("transfer_code") or event_id_str or uuid.uuid4())
                transfer_code = data.get("transfer_code")
                recipient = data.get("recipient") if isinstance(data.get("recipient"), dict) else {}
                reason = data.get("reason") or "Payout transfer"

                business = await _resolve_business(db, metadata)
                if not business:
                    logger.warning("No business found for Paystack transfer.success webhook")
                    return

                account = await _resolve_account(db, business, metadata, currency)
                category = await _resolve_category(db, business, metadata, "EXPENSE")
                user_id = await _resolve_user_id(db, business, metadata)
                ext_id = str(transfer_code or reference)

                # Check if transfer was already initiated/recorded in ledger
                stmt_tx = select(Transaction).where(Transaction.business_id == business.id)
                all_txs = (await db.execute(stmt_tx)).scalars().all()
                existing_tx = None
                for t in all_txs:
                    meta = t.sync_metadata or {}
                    if (
                        (reference and meta.get("reference") == reference)
                        or (transfer_code and meta.get("transfer_code") == transfer_code)
                        or (reference and reference in t.description)
                        or (transfer_code and transfer_code in t.description)
                    ):
                        existing_tx = t
                        break

                if existing_tx:
                    rec_stmt = select(ReconciliationRecord).where(
                        ReconciliationRecord.transaction_id == existing_tx.id
                    )
                    rec = (await db.execute(rec_stmt)).scalars().first()
                    if not rec:
                        rec = ReconciliationRecord(
                            id=uuid.uuid4(),
                            business_id=business.id,
                            transaction_id=existing_tx.id,
                            external_transaction_id=ext_id,
                            provider="paystack",
                            status="MATCHED",
                        )
                        db.add(rec)
                    else:
                        rec.status = "MATCHED"
                else:
                    rate, fx_snapshot = await FXService.get_or_create_rate_snapshot(
                        db=db,
                        base_currency=business.base_currency,
                        original_currency=currency,
                    )
                    base_amount = FXService.calculate_base_amount(amount, rate)

                    tx = Transaction(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        account_id=account.id,
                        category_id=category.id,
                        created_by_user_id=user_id,
                        type="EXPENSE",
                        original_amount=amount,
                        original_currency=currency,
                        base_currency_amount=base_amount,
                        exchange_rate_snapshot_id=fx_snapshot.id if fx_snapshot else None,
                        transaction_timestamp=datetime.now(timezone.utc),
                        description=f"Paystack payout transfer: {reason} ({ext_id})",
                        status="ACTIVE",
                        sync_metadata={
                            "provider": "paystack",
                            "transfer_code": transfer_code,
                            "reference": reference,
                            "recipient": recipient,
                            "event": "transfer.success",
                        },
                    )
                    db.add(tx)
                    if fx_snapshot:
                        fx_snapshot.transaction_id = tx.id

                    await BalanceService.update_balance_on_create(db, account, tx)

                    rec = ReconciliationRecord(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        transaction_id=tx.id,
                        external_transaction_id=ext_id,
                        provider="paystack",
                        status="MATCHED",
                    )
                    db.add(rec)

                    await AuditService.log_action(
                        db=db,
                        business_id=business.id,
                        actor_user_id=user_id,
                        entity_type="Transaction",
                        entity_id=tx.id,
                        action="CREATE",
                        before_values=None,
                        after_values={
                            "type": "EXPENSE",
                            "amount": str(amount),
                            "currency": currency,
                            "transfer_code": transfer_code,
                            "reference": reference,
                        },
                    )

            elif event_type in ("transfer.failed", "transfer.reversed"):
                # Handle failed or reversed transfers (re-credit ledger account)
                amount = Decimal(str(data.get("amount", 0))) / Decimal("100")
                currency = str(data.get("currency") or "GHS").upper()
                reference = str(data.get("reference") or data.get("transfer_code") or event_id_str or uuid.uuid4())
                transfer_code = data.get("transfer_code")
                reason = data.get("reason") or data.get("gateway_response") or f"Transfer {event_type}"

                business = await _resolve_business(db, metadata)
                if not business:
                    logger.warning("No business found for Paystack transfer failure/reversal webhook")
                    return

                account = await _resolve_account(db, business, metadata, currency)
                category = await _resolve_category(db, business, metadata, "INCOME")
                user_id = await _resolve_user_id(db, business, metadata)
                ext_id = str(transfer_code or reference)

                # Look for existing active expense transaction to void
                stmt_tx = select(Transaction).where(Transaction.business_id == business.id)
                all_txs = (await db.execute(stmt_tx)).scalars().all()
                existing_tx = None
                for t in all_txs:
                    meta = t.sync_metadata or {}
                    if (
                        (reference and meta.get("reference") == reference)
                        or (transfer_code and meta.get("transfer_code") == transfer_code)
                        or (reference and reference in t.description)
                        or (transfer_code and transfer_code in t.description)
                    ):
                        existing_tx = t
                        break

                if existing_tx and existing_tx.status == "ACTIVE" and existing_tx.type == "EXPENSE":
                    # Void the transaction: BalanceService reverses the impact and re-credits the account!
                    acc = await db.get(Account, existing_tx.account_id)
                    if acc:
                        await BalanceService.update_balance_on_void(db, acc, existing_tx)

                    rec_stmt = select(ReconciliationRecord).where(
                        ReconciliationRecord.transaction_id == existing_tx.id
                    )
                    rec = (await db.execute(rec_stmt)).scalars().first()
                    if rec:
                        rec.status = "REVERSED" if "reversed" in event_type else "FAILED"
                        rec.mismatch_reason = f"Paystack transfer marked {event_type}: {reason}"
                    else:
                        rec = ReconciliationRecord(
                            id=uuid.uuid4(),
                            business_id=business.id,
                            transaction_id=existing_tx.id,
                            external_transaction_id=ext_id,
                            provider="paystack",
                            status="REVERSED" if "reversed" in event_type else "FAILED",
                            mismatch_reason=f"Paystack transfer marked {event_type}: {reason}",
                        )
                        db.add(rec)

                    await AuditService.log_action(
                        db=db,
                        business_id=business.id,
                        actor_user_id=user_id,
                        entity_type="Transaction",
                        entity_id=existing_tx.id,
                        action="VOID",
                        before_values={"status": "ACTIVE"},
                        after_values={"status": "VOIDED", "reason": f"Paystack {event_type}: {reason}"},
                    )
                elif not (existing_tx and existing_tx.status == "VOIDED"):
                    # Record an INCOME reversal transaction to re-credit the ledger account
                    rate, fx_snapshot = await FXService.get_or_create_rate_snapshot(
                        db=db,
                        base_currency=business.base_currency,
                        original_currency=currency,
                    )
                    base_amount = FXService.calculate_base_amount(amount, rate)

                    reversal_tx = Transaction(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        account_id=account.id,
                        category_id=category.id,
                        created_by_user_id=user_id,
                        type="INCOME",
                        original_amount=amount,
                        original_currency=currency,
                        base_currency_amount=base_amount,
                        exchange_rate_snapshot_id=fx_snapshot.id if fx_snapshot else None,
                        transaction_timestamp=datetime.now(timezone.utc),
                        description=f"Paystack payout refund/reversal: {reason} ({ext_id})",
                        status="ACTIVE",
                        sync_metadata={
                            "provider": "paystack",
                            "transfer_code": transfer_code,
                            "reference": reference,
                            "event": event_type,
                            "reason": reason,
                        },
                    )
                    db.add(reversal_tx)
                    if fx_snapshot:
                        fx_snapshot.transaction_id = reversal_tx.id

                    await BalanceService.update_balance_on_create(db, account, reversal_tx)

                    rec = ReconciliationRecord(
                        id=uuid.uuid4(),
                        business_id=business.id,
                        transaction_id=reversal_tx.id,
                        external_transaction_id=ext_id,
                        provider="paystack",
                        status="RESOLVED",
                        mismatch_reason=f"Transfer {event_type} re-credited to ledger account: {reason}",
                    )
                    db.add(rec)

                    await AuditService.log_action(
                        db=db,
                        business_id=business.id,
                        actor_user_id=user_id,
                        entity_type="Transaction",
                        entity_id=reversal_tx.id,
                        action="CREATE",
                        before_values=None,
                        after_values={
                            "type": "INCOME",
                            "amount": str(amount),
                            "currency": currency,
                            "transfer_code": transfer_code,
                            "reference": reference,
                            "reason": f"Paystack {event_type}: {reason}",
                        },
                    )

            # Update WebhookEvent to PROCESSED
            if webhook_record:
                webhook_record.status = "PROCESSED"
                webhook_record.processed_at = datetime.now(timezone.utc)
                webhook_record.error_message = None

            await db.commit()

        except Exception as exc:
            await db.rollback()
            logger.error(f"Error processing Paystack background event: {exc}", exc_info=True)
            if webhook_record and event_id_str:
                try:
                    stmt = select(WebhookEvent).where(
                        WebhookEvent.provider == "paystack",
                        WebhookEvent.provider_event_id == event_id_str,
                    )
                    failed_rec = (await db.execute(stmt)).scalar_one_or_none()
                    if failed_rec:
                        failed_rec.status = "FAILED"
                        failed_rec.error_message = str(exc)[:1000]
                        await db.commit()
                except Exception:
                    pass
            raise exc


@router.post("/paystack", status_code=status.HTTP_200_OK)
async def paystack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_paystack_signature: Optional[str] = Header(None, alias="x-paystack-signature"),
    x_event_id: Optional[str] = Header(None, alias="X-Event-ID"),
    db: AsyncSession = Depends(get_db),
):
    # Optional IP validation (check proxy header if behind reverse proxy/Cloudflare)
    client_ip = request.client.host if request.client else None
    # if client_ip and client_ip not in PAYSTACK_IPS:
    #     raise HTTPException(status_code=403, detail="Unauthorized IP")

    # 1. Read raw body bytes for HMAC-SHA512 verification
    raw_body = await request.body()
    secret_key_str = os.environ.get("PAYSTACK_SECRET_KEY") or settings.PAYSTACK_SECRET_KEY or ""
    secret_key = secret_key_str.encode("utf-8")

    # If secret_key is set, enforce HMAC signature validation
    if secret_key:
        expected_sig = hmac.new(secret_key, raw_body, hashlib.sha512).hexdigest()
        if not x_paystack_signature or not hmac.compare_digest(expected_sig, x_paystack_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    elif x_paystack_signature:
        # If signature is provided while secret_key is not configured in env
        expected_sig = hmac.new(secret_key, raw_body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected_sig, x_paystack_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # 2. Parse event payload
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "Payload must be valid JSON"},
        )

    event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
    event_id = (
        x_event_id
        or event.get("id")
        or event.get("event_id")
        or event_data.get("id")
        or event_data.get("reference")
    )
    event_id_str = str(event_id) if event_id else None

    # 3. Idempotency check: prevent processing duplicate retries
    if event_id_str and event_id_str in PROCESSED_EVENTS:
        return {
            "status": "ok",
            "message": "Duplicate event ignored",
            "data": {
                "already_processed": True,
                "provider": "paystack",
                "provider_event_id": event_id_str,
            },
        }

    if event_id_str:
        # Also check DB for idempotency across app restarts
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider == "paystack",
            WebhookEvent.provider_event_id == event_id_str,
        )
        existing_event = (await db.execute(stmt)).scalar_one_or_none()
        if existing_event and existing_event.status == "PROCESSED":
            PROCESSED_EVENTS.add(event_id_str)
            return {
                "status": "ok",
                "message": "Duplicate event ignored",
                "data": {
                    "event_id": str(existing_event.id),
                    "provider": existing_event.provider,
                    "provider_event_id": existing_event.provider_event_id,
                    "status": existing_event.status,
                    "already_processed": True,
                },
            }

        PROCESSED_EVENTS.add(event_id_str)

    # 4. Offload processing to background task and return 200 OK immediately
    background_tasks.add_task(process_event_background, event)

    return {
        "status": "ok",
        "message": "Webhook received and processing scheduled",
        "data": {
            "provider": "paystack",
            "provider_event_id": event_id_str,
            "status": "PENDING",
            "already_processed": False,
        },
    }


@router.post("/{provider}", response_model=dict)
async def receive_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_event_id: str = Header(None, alias="X-Event-ID"),
):
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JSON", "message": "Payload must be valid JSON"},
        )

    # Extract event ID from headers or payload
    event_id = x_event_id or payload.get("id") or payload.get("event_id") or str(payload.get("data", {}).get("id"))
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_EVENT_ID", "message": "Provider event ID not found in payload or header"},
        )

    event_type = payload.get("event") or payload.get("type") or "generic.payment"

    webhook_event, already_processed = await WebhookService.process_webhook(
        db=db,
        provider=provider,
        provider_event_id=str(event_id),
        event_type=str(event_type),
        payload=payload,
    )

    await db.commit()

    return {
        "data": {
            "event_id": str(webhook_event.id),
            "provider": webhook_event.provider,
            "provider_event_id": webhook_event.provider_event_id,
            "status": webhook_event.status,
            "already_processed": already_processed,
        },
        "message": "Webhook processed idempotently",
    }
