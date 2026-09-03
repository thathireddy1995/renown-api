"""Customer saved prescription — /customer/prescription (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.customer_prescription import get_for_customer, to_out, upsert_for_customer
from app.database import get_db
from app.deps import get_current_customer
from app.dto.prescription_dto import CustomerPrescriptionOut, CustomerPrescriptionUpsert
from app.schemas import Customer

router = APIRouter(prefix="/customer/prescription", tags=["customer-prescription"])


@router.get("", response_model=CustomerPrescriptionOut)
@router.get("/", response_model=CustomerPrescriptionOut)
def get_prescription(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CustomerPrescriptionOut:
    row = get_for_customer(db, customer.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved prescription.")
    return to_out(row)


@router.put("", response_model=CustomerPrescriptionOut)
@router.put("/", response_model=CustomerPrescriptionOut)
def put_prescription(
    payload: CustomerPrescriptionUpsert,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CustomerPrescriptionOut:
    row = upsert_for_customer(db, customer.id, payload)
    db.commit()
    db.refresh(row)
    return to_out(row)
