import uuid
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.dependencies import (
    get_current_business,
    CurrentBusinessContext,
)
from backend.app.db.database import get_db
from backend.app.db.models import Transaction, Account
from backend.app.services.anomaly_service import AnomalyDetectionService
from backend.app.services.forecast_service import ForecastService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=dict)
async def get_financial_summary(
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    # Fetch accounts
    acc_stmt = select(Account).where(
        Account.business_id == ctx.business.id,
        Account.is_archived == False,
    )
    accounts = (await db.execute(acc_stmt)).scalars().all()

    total_account_balances = sum((acc.current_balance for acc in accounts), Decimal("0.00"))

    # Fetch total income & total expense for business
    tx_stmt = select(
        Transaction.type,
        func.sum(Transaction.base_currency_amount).label("total")
    ).where(
        Transaction.business_id == ctx.business.id,
        Transaction.status == "ACTIVE",
    ).group_by(Transaction.type)

    result = await db.execute(tx_stmt)
    totals_map = {row[0]: row[1] for row in result.all()}

    total_income = totals_map.get("INCOME", Decimal("0.00"))
    total_expense = totals_map.get("EXPENSE", Decimal("0.00"))
    net_cash_flow = total_income - total_expense

    return {
        "data": {
            "business_id": str(ctx.business.id),
            "base_currency": ctx.business.base_currency,
            "total_account_balance": float(total_account_balances),
            "total_income": float(total_income),
            "total_expense": float(total_expense),
            "net_cash_flow": float(net_cash_flow),
            "active_accounts_count": len(accounts),
        },
        "message": "Financial summary metrics generated",
    }


@router.get("/anomalies", response_model=dict)
async def get_financial_anomalies(
    sensitivity: float = Query(2.5, ge=1.0, le=5.0),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    anomalies_data = await AnomalyDetectionService.detect_anomalies(
        db=db,
        business_id=ctx.business.id,
        sensitivity=sensitivity,
    )
    return {
        "data": anomalies_data,
        "message": "Anomaly scan completed",
    }


@router.get("/forecast", response_model=dict)
async def get_cashflow_forecast(
    days_ahead: int = Query(30, ge=7, le=90),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    forecast_data = await ForecastService.generate_cashflow_forecast(
        db=db,
        business_id=ctx.business.id,
        days_ahead=days_ahead,
        base_currency=ctx.business.base_currency,
    )
    return {
        "data": forecast_data,
        "message": "Cash flow forecast generated",
    }
