from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Role, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import CustomerCreate, CustomerResponse, CustomerUpdate
from ..security import get_current_role
from ..services.secure_fields import encrypt_text, present_text_safe

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse], response_model_exclude_unset=True)
def list_customers(
    q: str | None = Query(default=None, max_length=160),
    db: Session = Depends(get_db),
    role: Role = Depends(get_current_role),
):
    if q and role != Role.owner:
        raise HTTPException(status_code=403, detail="Customer name search is only available to the owner.")
    customers = db.scalars(active_rows(select(Customer).order_by(Customer.id), Customer)).all()
    responses = []
    normalized_query = q.casefold() if q else None
    for customer in customers:
        name_result = present_text_safe(
            customer.name_encrypted, role, table="customers", row_id=customer.id, field="name"
        )
        contact_result = present_text_safe(
            customer.contact_encrypted, role, table="customers", row_id=customer.id, field="contact"
        )
        area_result = present_text_safe(
            customer.area_encrypted, role, table="customers", row_id=customer.id, field="area"
        )
        if normalized_query and (name_result.decrypt_failed or normalized_query not in name_result.value.casefold()):
            continue
        values = dict(
            id=customer.id,
            name=name_result.value,
            contact=contact_result.value,
            is_masked=role == Role.developer,
            decrypt_failed=name_result.decrypt_failed or contact_result.decrypt_failed or area_result.decrypt_failed,
        )
        if customer.area_encrypted is not None:
            values["area"] = area_result.value
        responses.append(CustomerResponse(**values))
    return responses


@router.post("", response_model=CustomerResponse, status_code=201, response_model_exclude_unset=True)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), role: Role = Depends(get_current_role)):
    customer = Customer(
        name_encrypted=encrypt_text(payload.name).encode("ascii"),
        contact_encrypted=encrypt_text(payload.contact).encode("ascii"),
        area_encrypted=encrypt_text(payload.area.strip()).encode("ascii") if payload.area and payload.area.strip() else None,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    name_result = present_text_safe(
        customer.name_encrypted, role, table="customers", row_id=customer.id, field="name"
    )
    contact_result = present_text_safe(
        customer.contact_encrypted, role, table="customers", row_id=customer.id, field="contact"
    )
    area_result = present_text_safe(
        customer.area_encrypted, role, table="customers", row_id=customer.id, field="area"
    )
    values = dict(
        id=customer.id,
        name=name_result.value,
        contact=contact_result.value,
        is_masked=role == Role.developer,
        decrypt_failed=name_result.decrypt_failed or contact_result.decrypt_failed or area_result.decrypt_failed,
    )
    if customer.area_encrypted is not None:
        values["area"] = area_result.value
    return CustomerResponse(**values)


@router.patch("/{customer_id}", response_model=CustomerResponse, response_model_exclude_unset=True)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    role: Role = Depends(get_current_role),
):
    customer = get_active(db, Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field == "name" and value is None:
            raise HTTPException(status_code=422, detail="Customer name cannot be empty")
        encrypted_field = f"{field}_encrypted"
        cleaned = value.strip() if isinstance(value, str) else value
        setattr(customer, encrypted_field, encrypt_text(cleaned).encode("ascii") if cleaned else None)
    db.commit()
    db.refresh(customer)
    name = present_text_safe(customer.name_encrypted, role, table="customers", row_id=customer.id, field="name")
    contact = present_text_safe(customer.contact_encrypted, role, table="customers", row_id=customer.id, field="contact")
    area = present_text_safe(customer.area_encrypted, role, table="customers", row_id=customer.id, field="area")
    values = dict(
        id=customer.id,
        name=name.value,
        contact=contact.value if customer.contact_encrypted else "",
        is_masked=role == Role.developer,
        decrypt_failed=name.decrypt_failed or contact.decrypt_failed or area.decrypt_failed,
    )
    if customer.area_encrypted is not None or "area" in changes:
        values["area"] = area.value if customer.area_encrypted else ""
    return CustomerResponse(**values)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_role)):
    customer = get_active(db, Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204)
