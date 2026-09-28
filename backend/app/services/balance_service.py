import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import Account, Transaction


class BalanceService:
    @staticmethod
    def _calculate_effective_amount(tx_type: str, original_amount: Decimal, original_currency: str, account_currency: str, base_currency_amount: Decimal) -> Decimal:
        # Determine the net impact on the account balance
        # If original currency matches account currency, use original_amount
        # Otherwise, use the converted base_currency_amount
        amount = original_amount if original_currency.upper() == account_currency.upper() else base_currency_amount
        return amount if tx_type.upper() == "INCOME" else -amount

    @classmethod
    async def update_balance_on_create(cls, db: AsyncSession, account: Account, transaction: Transaction) -> Decimal:
        if transaction.status.upper() == "ACTIVE":
            impact = cls._calculate_effective_amount(
                transaction.type,
                transaction.original_amount,
                transaction.original_currency,
                account.currency,
                transaction.base_currency_amount,
            )
            account.current_balance = Decimal(str(account.current_balance)) + impact
        return account.current_balance

    @classmethod
    async def update_balance_on_edit(
        cls,
        db: AsyncSession,
        account: Account,
        old_type: str,
        old_amount: Decimal,
        old_currency: str,
        old_base_amount: Decimal,
        old_status: str,
        new_transaction: Transaction,
    ) -> Decimal:
        # 1. Reverse old transaction impact if it was active
        if old_status.upper() == "ACTIVE":
            old_impact = cls._calculate_effective_amount(
                old_type, old_amount, old_currency, account.currency, old_base_amount
            )
            account.current_balance = Decimal(str(account.current_balance)) - old_impact

        # 2. Apply new transaction impact if active
        if new_transaction.status.upper() == "ACTIVE":
            new_impact = cls._calculate_effective_amount(
                new_transaction.type,
                new_transaction.original_amount,
                new_transaction.original_currency,
                account.currency,
                new_transaction.base_currency_amount,
            )
            account.current_balance = Decimal(str(account.current_balance)) + new_impact

        return account.current_balance

    @classmethod
    async def update_balance_on_void(cls, db: AsyncSession, account: Account, transaction: Transaction) -> Decimal:
        # Reversing an active transaction
        if transaction.status.upper() == "ACTIVE":
            impact = cls._calculate_effective_amount(
                transaction.type,
                transaction.original_amount,
                transaction.original_currency,
                account.currency,
                transaction.base_currency_amount,
            )
            account.current_balance = Decimal(str(account.current_balance)) - impact
            transaction.status = "VOIDED"
        return account.current_balance

    @classmethod
    async def reconstruct_balance_as_of(cls, db: AsyncSession, account: Account, target_timestamp: datetime) -> Decimal:
        # Query active transactions up to target_timestamp
        stmt = select(Transaction).where(
            Transaction.account_id == account.id,
            Transaction.status == "ACTIVE",
            Transaction.transaction_timestamp <= target_timestamp,
        )
        result = await db.execute(stmt)
        transactions = result.scalars().all()

        balance = Decimal(str(account.opening_balance))
        for tx in transactions:
            impact = cls._calculate_effective_amount(
                tx.type,
                tx.original_amount,
                tx.original_currency,
                account.currency,
                tx.base_currency_amount,
            )
            balance += impact

        return balance
