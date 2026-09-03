from typing import Any

from fastapi import HTTPException
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import Select

MAX_LIMIT = 200


def paginate(stmt: Select, skip: int = 0, limit: int = 50) -> Select:
    skip = max(0, skip)
    limit = min(max(1, limit), MAX_LIMIT)
    return stmt.offset(skip).limit(limit)


def apply_sort(
    stmt: Select,
    sort_fields: dict[str, InstrumentedAttribute[Any]],
    sort: str | None = None,
) -> Select:
    if not sort:
        return stmt.order_by(desc("created_at"))
    descending = sort.startswith("-")
    field_name = sort[1:] if descending else sort
    column = sort_fields.get(field_name)
    if column is None:
        raise HTTPException(status_code=422, detail=f"Unsupported sort field: {field_name}")
    return stmt.order_by(desc(column) if descending else asc(column))


def prepare_search(
    stmt: Select,
    columns: list[InstrumentedAttribute[Any]],
    q: str | None = None,
) -> Select:
    if not q:
        return stmt
    pattern = f"%{q.strip()}%"
    if pattern == "%%":
        return stmt
    return stmt.where(or_(*[c.ilike(pattern) for c in columns]))


async def total_count(db, stmt: Select) -> int:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    result = await db.execute(count_stmt)
    return int(result.scalar_one())