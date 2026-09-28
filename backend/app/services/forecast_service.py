import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models import Transaction


class ForecastService:
    @classmethod
    async def generate_cashflow_forecast(
        cls,
        db: AsyncSession,
        business_id: uuid.UUID,
        days_ahead: int = 30,
        base_currency: str = "USD",
    ) -> Dict[str, Any]:
        """
        Generates moving-average baseline cash flow forecasts with uncertainty bounds.
        """
        # Fetch active transactions for business
        stmt = select(Transaction).where(
            Transaction.business_id == business_id,
            Transaction.status == "ACTIVE",
        ).order_by(Transaction.transaction_timestamp.asc())
        
        result = await db.execute(stmt)
        transactions = result.scalars().all()

        if not transactions:
            return {
                "forecast_available": False,
                "reason": "Insufficient transaction history. At least 30 days of data required.",
                "days_ahead": days_ahead,
                "data_points": 0,
                "forecast": [],
            }

        first_tx = transactions[0]
        tx_ts = first_tx.transaction_timestamp
        if tx_ts.tzinfo is None:
            tx_ts = tx_ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        history_days = max((now - tx_ts).days, 1)

        if history_days < settings.FORECAST_MINIMUM_HISTORY_DAYS and len(transactions) < 10:
            return {
                "forecast_available": False,
                "reason": f"Insufficient historical data ({history_days} days present; minimum {settings.FORECAST_MINIMUM_HISTORY_DAYS} days required).",
                "days_ahead": days_ahead,
                "history_days_present": history_days,
                "forecast": [],
            }

        # Calculate historical daily averages for income and expense
        total_income = sum(tx.base_currency_amount for tx in transactions if tx.type.upper() == "INCOME")
        total_expense = sum(tx.base_currency_amount for tx in transactions if tx.type.upper() == "EXPENSE")

        daily_income_avg = total_income / Decimal(str(history_days))
        daily_expense_avg = total_expense / Decimal(str(history_days))
        daily_net_avg = daily_income_avg - daily_expense_avg

        # Generate future forecast points with uncertainty bounds (±15% to ±25%)
        forecast_points = []
        cumulative_net = Decimal("0.00")

        for day in range(1, days_ahead + 1):
            target_date = (now + timedelta(days=day)).date().isoformat()
            cumulative_net += daily_net_avg

            # Uncertainty expands as projection horizon increases
            uncertainty_factor = Decimal(str(0.10 + (day / days_ahead) * 0.15))
            margin = abs(cumulative_net) * uncertainty_factor if cumulative_net != 0 else Decimal("50.00")

            forecast_points.append({
                "date": target_date,
                "predicted_net": round(float(cumulative_net), 2),
                "lower_bound": round(float(cumulative_net - margin), 2),
                "upper_bound": round(float(cumulative_net + margin), 2),
                "projected_daily_income": round(float(daily_income_avg), 2),
                "projected_daily_expense": round(float(daily_expense_avg), 2),
            })

        return {
            "forecast_available": True,
            "currency": base_currency,
            "history_days_analyzed": history_days,
            "days_ahead": days_ahead,
            "forecast": forecast_points,
            "disclaimer": "Forecast is based on moving averages of historical transaction data and represents statistical estimation, not a guaranteed financial outcome.",
        }
