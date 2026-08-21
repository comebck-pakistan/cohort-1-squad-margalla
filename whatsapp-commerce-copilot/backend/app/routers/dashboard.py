"""Read-only merchant dashboard overview.

One endpoint backs the whole overview screen so every card, the activity feed and
the attention list are computed from the same period and the same query pass —
separate endpoints would let the cards disagree with each other mid-refresh.

Everything here is store-scoped and derived from persisted rows. Nothing is
estimated or synthesised: if the schema cannot support a number honestly it is
not returned.
"""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.store import Store
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.handoff import HumanHandoff
from app.models.order import Order
from app.schemas.api import (
    DashboardOverviewResponse, DashboardPeriod, DashboardMetrics,
    DashboardActivityItem, DashboardAttentionItem,
)
from app.utils.phone import mask_phone_number

router = APIRouter(prefix="/api/stores/{store_id}", tags=["dashboard"])

# Every timestamp in the database is a NAIVE UTC value (models default to
# ``datetime.utcnow()``). The merchants this product serves are in Pakistan and
# `stores` has no timezone column, so day boundaries are resolved in a single
# documented business timezone rather than the server's locale. Changing this to
# a per-store setting later only requires sourcing the zone from the Store row.
BUSINESS_TZ = ZoneInfo("Asia/Karachi")
BUSINESS_TZ_NAME = "Asia/Karachi"

# An order is "confirmed" for dashboard purposes once it is persisted; only an
# explicit cancellation removes it from the counts and from revenue.
CANCELLED_STATUS = "cancelled"
# Handoffs the merchant still has to deal with.
UNRESOLVED_HANDOFF_STATUSES = ("pending", "active")

VALID_RANGES = ("today", "yesterday", "7d", "30d", "all", "custom")

# Handoff summaries are built as "Customer: <their message>", so they can carry
# whatever the customer typed. The merchant needs enough to triage, and opens the
# conversation for the rest — so only a short snippet is surfaced here.
SUMMARY_SNIPPET_CHARS = 140


def _summary_snippet(summary: str | None) -> str | None:
    if not summary:
        return None
    text = " ".join(summary.split())
    if len(text) <= SUMMARY_SNIPPET_CHARS:
        return text
    return text[:SUMMARY_SNIPPET_CHARS].rstrip() + "…"


def _utc_bounds(start_local_date: date, end_local_date: date) -> tuple[datetime, datetime]:
    """Local inclusive day range -> naive-UTC half-open [start, end) bounds.

    The end date is inclusive for the merchant ("Last 7 days" includes today), so
    the upper bound is the start of the *next* local day. Using a half-open range
    avoids the off-by-one that ``<= end_of_day`` introduces at microsecond
    precision.
    """
    start_local = datetime.combine(start_local_date, time.min, tzinfo=BUSINESS_TZ)
    end_local = datetime.combine(end_local_date + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _resolve_period(range_: str, start_date: str | None, end_date: str | None):
    """Resolve the requested range into naive-UTC query bounds.

    Returns ``(label, start_utc, end_utc)`` where the bounds may be ``None`` for
    the unbounded "all time" range.
    """
    today_local = datetime.now(BUSINESS_TZ).date()

    if start_date or end_date:
        if not (start_date and end_date):
            raise HTTPException(400, "Both start_date and end_date are required for a custom range")
        try:
            start_parsed = date.fromisoformat(start_date)
            end_parsed = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(400, "start_date and end_date must be YYYY-MM-DD")
        if end_parsed < start_parsed:
            raise HTTPException(400, "end_date must not be before start_date")
        start_utc, end_utc = _utc_bounds(start_parsed, end_parsed)
        return "custom", start_utc, end_utc

    if range_ not in VALID_RANGES:
        raise HTTPException(400, f"range must be one of: {', '.join(VALID_RANGES)}")

    if range_ == "all":
        return "all", None, None
    if range_ == "today":
        start_utc, end_utc = _utc_bounds(today_local, today_local)
    elif range_ == "yesterday":
        y = today_local - timedelta(days=1)
        start_utc, end_utc = _utc_bounds(y, y)
    elif range_ == "30d":
        start_utc, end_utc = _utc_bounds(today_local - timedelta(days=29), today_local)
    else:  # "7d" (default) and "custom" without dates
        range_ = "7d"
        start_utc, end_utc = _utc_bounds(today_local - timedelta(days=6), today_local)
    return range_, start_utc, end_utc


def _iso(dt: datetime | None) -> str | None:
    """Naive-UTC column value -> timezone-aware ISO string."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _within(column, start_utc, end_utc):
    """Period predicate for a timestamp column ('all time' adds no constraint)."""
    if start_utc is None:
        return []
    return [column >= start_utc, column < end_utc]


async def _get_store(store_id: str, db: AsyncSession) -> Store:
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Store not found")
    return store


@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    store_id: str,
    range: str = Query("7d", description="today|yesterday|7d|30d|all"),
    start_date: str | None = Query(None, description="YYYY-MM-DD (with end_date)"),
    end_date: str | None = Query(None, description="YYYY-MM-DD (with start_date)"),
    activity_limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:
    """Aggregate the merchant's activity for one period. Read-only."""
    await _get_store(store_id, db)
    range_label, start_utc, end_utc = _resolve_period(range, start_date, end_date)

    order_period = _within(Order.created_at, start_utc, end_utc)
    live_order_filters = [
        Order.store_id == store_id,
        Order.status != CANCELLED_STATUS,
        *order_period,
    ]

    # --- Metrics (aggregated in the database, never by loading rows) ---
    orders_row = (await db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0.0),
        ).where(*live_order_filters)
    )).one()
    orders_confirmed, revenue = int(orders_row[0]), float(orders_row[1])

    orders_cancelled = int((await db.execute(
        select(func.count(Order.id)).where(
            Order.store_id == store_id,
            Order.status == CANCELLED_STATUS,
            *_within(Order.updated_at, start_utc, end_utc),
        )
    )).scalar_one())

    # "Handled" = conversations that actually received a customer message in the
    # period. Message has no store_id, so scoping goes through the conversation.
    inbound_filters = [
        Conversation.store_id == store_id,
        Message.direction == "inbound",
        *_within(Message.created_at, start_utc, end_utc),
    ]
    conv_row = (await db.execute(
        select(
            func.count(func.distinct(Message.conversation_id)),
            func.count(Message.id),
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*inbound_filters)
    )).one()
    conversations_handled, inbound_messages = int(conv_row[0]), int(conv_row[1])

    handoff_filters = [
        HumanHandoff.store_id == store_id,
        HumanHandoff.status.in_(UNRESOLVED_HANDOFF_STATUSES),
        *_within(HumanHandoff.created_at, start_utc, end_utc),
    ]
    needs_attention = int((await db.execute(
        select(func.count(HumanHandoff.id)).where(*handoff_filters)
    )).scalar_one())

    # --- Attention list (same definition as the count above, so they agree) ---
    handoffs = (await db.execute(
        select(HumanHandoff, Customer.phone_number)
        .join(Conversation, Conversation.id == HumanHandoff.conversation_id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(*handoff_filters)
        .order_by(HumanHandoff.created_at.desc())
        .limit(activity_limit)
    )).all()
    attention_items = [
        DashboardAttentionItem(
            id=h.id,
            conversation_id=h.conversation_id,
            reason=h.reason,
            summary=_summary_snippet(h.summary),
            status=h.status,
            customer_phone_masked=mask_phone_number(phone),
            created_at=_iso(h.created_at),
        )
        for h, phone in handoffs
    ]

    activity = await _build_activity(db, store_id, start_utc, end_utc, activity_limit)

    return DashboardOverviewResponse(
        store_id=store_id,
        period=DashboardPeriod(
            range=range_label,
            start=_iso(start_utc) or "",
            end=_iso(end_utc) or "",
            timezone=BUSINESS_TZ_NAME,
        ),
        metrics=DashboardMetrics(
            conversations_handled=conversations_handled,
            inbound_messages=inbound_messages,
            orders_confirmed=orders_confirmed,
            orders_cancelled=orders_cancelled,
            revenue_pkr=round(revenue, 2),
            needs_attention=needs_attention,
        ),
        activity=activity,
        attention_items=attention_items,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


async def _build_activity(
    db: AsyncSession, store_id: str, start_utc, end_utc, limit: int,
) -> list[DashboardActivityItem]:
    """Combine real rows from orders, conversations and handoffs, newest first.

    There is no event table, and adding one would mean rewriting how the message
    pipeline records state. Instead each source contributes at most `limit` rows
    and they are merged in memory — bounded work, no full-table scans.
    """
    items: list[tuple[datetime, DashboardActivityItem]] = []

    orders = (await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.store_id == store_id,
               *_within(Order.created_at, start_utc, end_utc))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )).scalars().all()
    for o in orders:
        if o.status == CANCELLED_STATUS:
            continue  # emitted below against its cancellation time
        items.append((o.created_at, DashboardActivityItem(
            id=f"order:{o.id}",
            type="order_confirmed",
            description=_order_description(o, "Order confirmed"),
            created_at=_iso(o.created_at),
            order_id=o.id,
            conversation_id=o.conversation_id,
        )))

    # Cancellations have no dedicated timestamp; `updated_at` is when the row was
    # last written, which for a cancelled order is the cancellation. Approximate
    # but derived from real data, never invented.
    cancelled = (await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.store_id == store_id,
            Order.status == CANCELLED_STATUS,
            *_within(Order.updated_at, start_utc, end_utc),
        )
        .order_by(Order.updated_at.desc())
        .limit(limit)
    )).scalars().all()
    for o in cancelled:
        items.append((o.updated_at, DashboardActivityItem(
            id=f"order-cancelled:{o.id}",
            type="order_cancelled",
            description=_order_description(o, "Order cancelled"),
            created_at=_iso(o.updated_at),
            order_id=o.id,
            conversation_id=o.conversation_id,
        )))

    conversations = (await db.execute(
        select(Conversation)
        .where(Conversation.store_id == store_id,
               *_within(Conversation.created_at, start_utc, end_utc))
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )).scalars().all()
    for c in conversations:
        items.append((c.created_at, DashboardActivityItem(
            id=f"conversation:{c.id}",
            type="conversation_started",
            description="New customer conversation started",
            created_at=_iso(c.created_at),
            conversation_id=c.id,
        )))

    handoffs = (await db.execute(
        select(HumanHandoff)
        .where(HumanHandoff.store_id == store_id,
               *_within(HumanHandoff.created_at, start_utc, end_utc))
        .order_by(HumanHandoff.created_at.desc())
        .limit(limit)
    )).scalars().all()
    for h in handoffs:
        items.append((h.created_at, DashboardActivityItem(
            id=f"handoff:{h.id}",
            type="escalation",
            description=f"Escalated to you — {h.reason.replace('_', ' ')}",
            created_at=_iso(h.created_at),
            conversation_id=h.conversation_id,
        )))

    items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in items[:limit]]


def _order_description(order: Order, prefix: str) -> str:
    """Describe an order from its own persisted line items. No customer data."""
    parts = []
    for it in order.items:
        label = it.product_name
        if it.variant_description:
            label = f"{label} ({it.variant_description})"
        if it.quantity and it.quantity > 1:
            label = f"{label} ×{it.quantity}"
        parts.append(label)
    detail = ", ".join(parts) if parts else "order"
    return f"{prefix} — {detail} · PKR {order.total_amount:,.0f}"
