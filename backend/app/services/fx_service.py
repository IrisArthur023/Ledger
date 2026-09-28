import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import ExchangeRateSnapshot


class FXService:
    @staticmethod
    async def get_or_create_rate_snapshot(
        db: AsyncSession,
        base_currency: str,
        original_currency: str,
        manual_rate: Optional[Decimal] = None,
        transaction_id: Optional[uuid.UUID] = None,
    ) -> Tuple[Decimal, Optional[ExchangeRateSnapshot]]:
        base_curr = base_currency.upper()
        orig_curr = original_currency.upper()

        if base_curr == orig_curr:
            return Decimal("1.000000"), None

        rate: Decimal
        source: str = "MANUAL"

        if manual_rate is not None:
            rate = Decimal(str(manual_rate))
        else:
            # Default mock/stub conversion rates for dev/testing when provider not configured
            # e.g., 1 USD = 12.5 GHS, 1 EUR = 1.1 USD, etc.
            rates_pair = (orig_curr, base_curr)
            default_matrix = {
                ("USD", "GHS"): Decimal("12.500000"),
                ("GHS", "USD"): Decimal("0.080000"),
                ("EUR", "USD"): Decimal("1.100000"),
                ("USD", "EUR"): Decimal("0.909091"),
                ("GBP", "USD"): Decimal("1.280000"),
                ("USD", "GBP"): Decimal("0.781250"),
            }
            rate = default_matrix.get(rates_pair, Decimal("1.000000"))
            source = "PROVIDER_FALLBACK"

        snapshot = ExchangeRateSnapshot(
            id=uuid.uuid4(),
            transaction_id=transaction_id,
            base_currency=base_curr,
            original_currency=orig_curr,
            rate=rate,
            source=source,
            captured_at=datetime.now(timezone.utc),
        )
        db.add(snapshot)
        return rate, snapshot

    @classmethod
    def calculate_base_amount(cls, amount: Decimal, rate: Decimal) -> Decimal:
        return (Decimal(str(amount)) * Decimal(str(rate))).quantize(Decimal("0.0001"))
