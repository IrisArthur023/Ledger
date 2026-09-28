import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.dependencies import (
    get_current_business,
    CurrentBusinessContext,
    require_manager,
)
from backend.app.db.database import get_db
from backend.app.db.models import Category
from backend.app.modules.category.schemas import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
)

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    category = Category(
        id=uuid.uuid4(),
        business_id=ctx.business.id,
        name=body.name,
        type=body.type.upper(),
        is_default=False,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    return {
        "data": CategoryResponse.model_validate(category),
        "message": "Category created successfully",
    }


@router.get("", response_model=dict)
async def list_categories(
    type_filter: Optional[str] = Query(None, alias="type"),
    ctx: CurrentBusinessContext = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Category).where(Category.business_id == ctx.business.id)
    if type_filter:
        stmt = stmt.where(Category.type == type_filter.upper())

    stmt = stmt.order_by(Category.name.asc())
    result = await db.execute(stmt)
    categories = result.scalars().all()

    return {
        "data": [CategoryResponse.model_validate(c) for c in categories],
        "message": f"Retrieved {len(categories)} categories",
    }


@router.put("/{category_id}", response_model=dict)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    ctx: CurrentBusinessContext = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Category).where(
        Category.id == category_id,
        Category.business_id == ctx.business.id,
    )
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "Category not found"},
        )

    if body.name is not None:
        category.name = body.name
    if body.type is not None:
        category.type = body.type.upper()

    await db.commit()
    await db.refresh(category)

    return {
        "data": CategoryResponse.model_validate(category),
        "message": "Category updated successfully",
    }
