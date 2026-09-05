"""Customer saved prescription — /customer/prescription (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import S3_PUBLIC_BUCKET
from app.core.customer_prescription import get_for_customer, to_out, upsert_for_customer
from app.core.s3_images import presign_prescription_puts
from app.database import get_db
from app.deps import get_current_customer
from app.dto.catalog_dto import ImagePresignItem, ImagePresignRequest, ImagePresignResponse
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


@router.post("/upload/presign", response_model=ImagePresignResponse)
def presign_prescription_upload(
    payload: ImagePresignRequest,
    customer: Customer = Depends(get_current_customer),
) -> ImagePresignResponse:
    if len(payload.files) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload one prescription file at a time.",
        )
    uploads = presign_prescription_puts(
        customer.id,
        [(f.filename, f.content_type) for f in payload.files],
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )
