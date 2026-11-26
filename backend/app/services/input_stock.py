from sqlalchemy.orm import Session

from ..models import InputApplication, InputItem, Product
from .products_stock import record_movement, void_source_movements
from .source_types import INPUT_APPLICATION


def validate_input_product(db: Session, product_id: int | None) -> None:
    if product_id is None:
        return
    product = db.get(Product, product_id)
    if product is None or product.deleted_at is not None or not product.is_active:
        raise ValueError("Product is not available")


def sync_input_application_stock(
    db: Session,
    application: InputApplication,
    item_quantities: list[tuple[InputItem, float]],
) -> list[str]:
    """Replace an application's active stock deductions using request quantities."""
    void_source_movements(db, INPUT_APPLICATION, application.id)
    warnings: set[str] = set()
    for item, quantity in item_quantities:
        if item.product_id is None:
            continue
        product = db.get(Product, item.product_id)
        if product is None or product.deleted_at is not None or not product.is_active:
            raise ValueError("Product is not available")
        unit = (item.unit or "").strip() or product.unit
        try:
            record_movement(
                db,
                product.id,
                -float(quantity),
                unit,
                "application",
                source_type=INPUT_APPLICATION,
                source_id=application.id,
            )
        except ValueError as exc:
            if str(exc) == "Invalid quantity or unit":
                warnings.add(f"unit_mismatch:{product.id}")
                continue
            raise
    return sorted(warnings)
