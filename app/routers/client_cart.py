import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import require_cliente
from app.models import Quote, User
from app.schemas import (
    CartValidateIn,
    CartValidationOut,
    OrderCreateIn,
    OrderCreatedOut,
    PaginatedQuotes,
)
from app.services.cart import normalize_cart_quantities, resolve_cart
from app.services.quotes import create_order, expire_pending_orders, serialize_quote

router = APIRouter(prefix="/api/cliente", tags=["cliente · carrito"])


@router.post("/carrito/validar", response_model=CartValidationOut)
def validate_cart(
    payload: CartValidateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_cliente),
) -> dict:
    """Valida el carrito local del cliente contra el catálogo vigente.

    No devuelve precios ni stock exacto: solo si cada línea se puede atender y
    si todavía se puede aumentar la cantidad.
    """
    quantities = normalize_cart_quantities(
        (item.presentation_id, item.quantity) for item in payload.items
    )
    return resolve_cart(db, quantities)


@router.post(
    "/carrito/pedido",
    response_model=OrderCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def place_order(
    payload: OrderCreateIn,
    db: Session = Depends(get_db),
    client: User = Depends(require_cliente),
) -> dict:
    """Convierte el carrito del cliente en un pedido pendiente de revisión."""
    quantities = normalize_cart_quantities(
        (item.presentation_id, item.quantity) for item in payload.items
    )
    quote = create_order(db, quantities, client)
    return {
        "id": quote.id,
        "status": quote.status,
        "total_units": quote.total_units,
        "created_at": quote.created_at,
        "expires_at": quote.expires_at,
    }


@router.get("/pedidos", response_model=PaginatedQuotes)
def list_client_orders(
    estado: str | None = Query(
        default=None, pattern="^(pendiente|confirmada|cancelada)$"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    client: User = Depends(require_cliente),
) -> dict:
    """Devuelve únicamente los pedidos del cliente autenticado."""
    expire_pending_orders(db)

    conditions = [Quote.client_id == client.id]
    if estado:
        conditions.append(Quote.status == estado)

    total = db.scalar(select(func.count(Quote.id)).where(*conditions)) or 0
    quotes = db.scalars(
        select(Quote)
        .where(*conditions)
        .options(
            selectinload(Quote.items),
            selectinload(Quote.client),
            selectinload(Quote.confirmed_by),
            selectinload(Quote.cancelled_by),
        )
        .order_by(Quote.created_at.desc(), Quote.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [serialize_quote(quote) for quote in quotes],
        "total": total,
        "page": page,
        "pages": math.ceil(total / page_size) if total else 0,
        "page_size": page_size,
    }
