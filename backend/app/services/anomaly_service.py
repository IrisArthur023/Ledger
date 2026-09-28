import uuid
import math
from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models import Transaction


class AnomalyDetectionService:
    @classmethod
    async def detect_anomalies(
        cls,
        db: AsyncSession,
        business_id: uuid.UUID,
        sensitivity: float = settings.ANOMALY_SENSITIVITY,
    ) -> Dict[str, Any]:
        """
        Detects financial anomalies for a business relative to its own historical baseline.
        """
        stmt = select(Transaction).where(
            Transaction.business_id == business_id,
            Transaction.status == "ACTIVE",
        ).order_by(Transaction.transaction_timestamp.desc())

        result = await db.execute(stmt)
        transactions = result.scalars().all()

        if len(transactions) < 5:
            return {
                "anomalies_found": 0,
                "reason": "Insufficient transaction volume (minimum 5 transactions required for statistical baseline).",
                "anomalies": [],
            }

        amounts = [float(tx.base_currency_amount) for tx in transactions]
        mean_amount = sum(amounts) / len(amounts)
        variance = sum((x - mean_amount) ** 2 for x in amounts) / len(amounts)
        std_dev = math.sqrt(variance)

        detected_anomalies = []

        for tx in transactions:
            amt = float(tx.base_currency_amount)
            z_score = (amt - mean_amount) / std_dev if std_dev > 0 else 0.0

            signals = []
            if abs(z_score) >= sensitivity:
                signals.append(f"Unusually large transaction amount ({amt:.2f} vs business average {mean_amount:.2f}, z-score: {z_score:.2f})")
            
            # Additional heuristic checks
            if tx.transaction_timestamp.hour < 5 or tx.transaction_timestamp.hour > 23:
                signals.append(f"Transaction recorded at unusual hour ({tx.transaction_timestamp.hour:02d}:00 UTC)")

            if signals:
                detected_anomalies.append({
                    "transaction_id": str(tx.id),
                    "amount": float(tx.original_amount),
                    "currency": tx.original_currency,
                    "base_currency_amount": amt,
                    "description": tx.description,
                    "type": tx.type,
                    "timestamp": tx.transaction_timestamp.isoformat(),
                    "z_score": round(z_score, 2),
                    "signals": signals,
                    "risk_score": min(round(abs(z_score) * 20 + len(signals) * 15, 1), 100.0),
                })

        return {
            "business_id": str(business_id),
            "total_transactions_analyzed": len(transactions),
            "historical_mean_amount": round(mean_amount, 2),
            "historical_std_dev": round(std_dev, 2),
            "sensitivity_threshold": sensitivity,
            "anomalies_found": len(detected_anomalies),
            "anomalies": detected_anomalies,
        }
