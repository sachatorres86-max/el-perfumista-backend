from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import STAFF_ROLES, get_optional_user
from app.models import User
from app.schemas import SharedCartOut
from app.services.cart import resolve_cart
from app.services.cart_token import InvalidCartToken, decode_cart_token

router = APIRouter(prefix="/api/cotizaciones", tags=["cotizaciones compartidas"])


@router.get("/{token}", response_model=SharedCartOut)
def read_shared_cart(
    token: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> dict:
    """Muestra el carrito de un enlace compartido.

    El personal autorizado ve precios y total de referencia; los clientes y
    visitantes anónimos solo ven la selección, sin precios ni stock exacto.
    """
    try:
        quantities = decode_cart_token(token)
    except InvalidCartToken:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enlace de cotización inválido o incompleto",
        )

    is_staff = viewer is not None and viewer.role in STAFF_ROLES
    cart = resolve_cart(db, quantities, include_prices=is_staff)

    if viewer is None:
        viewer_role = "anonimo"
    else:
        viewer_role = viewer.role.value

    total_cop = None
    if is_staff:
        total_cop = sum(line.get("line_total_cop") or 0 for line in cart["items"])

    return {**cart, "viewer_role": viewer_role, "total_cop": total_cop}
