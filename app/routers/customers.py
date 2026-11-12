from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Role, utc_now
from ..query_helpers import active_rows, get_active
from ..schemas import CustomerCreate, CustomerResponse
from ..security import get_current_role
from ..services.secure_fields import encrypt_text, present_text_safe

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
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
        if normalized_query and (name_result.decrypt_failed or normalized_query not in name_result.value.casefold()):
            continue
        responses.append(CustomerResponse(
            id=customer.id,
            name=name_result.value,
            contact=contact_result.value,
            is_masked=role == Role.developer,
            decrypt_failed=name_result.decrypt_failed or contact_result.decrypt_failed,
        ))
    return responses


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), role: Role = Depends(get_current_role)):
    customer = Customer(
        name_encrypted=encrypt_text(payload.name).encode("ascii"),
        contact_encrypted=encrypt_text(payload.contact).encode("ascii"),
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
    return CustomerResponse(
        id=customer.id,
        name=name_result.value,
        contact=contact_result.value,
        is_masked=role == Role.developer,
        decrypt_failed=name_result.decrypt_failed or contact_result.decrypt_failed,
    )


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_role)):
    customer = get_active(db, Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204)
