import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import (
    DEMO_OTP_CODE,
    IS_PRODUCTION,
    OTP_EXPIRY_MINUTES,
    OTP_MAX_ATTEMPTS,
    OTP_RATE_LIMIT_MAX,
    OTP_RATE_LIMIT_WINDOW_MINUTES,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.dto.customer_auth_dto import (
    CustomerLoginRequest,
    CustomerOut,
    CustomerTokenResponse,
    ForgotPasswordCompleteRequest,
    ForgotPasswordRequestOtp,
    GoogleAuthRequest,
    OtpRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
    RegisterCompleteRequest,
    RegisterRequestOtp,
)
from app.schemas import Customer, OtpCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customer/auth", tags=["customer-auth"])

# Must match customer-renown VITE_GOOGLE_CLIENT_ID / hardcoded client id.
GOOGLE_CLIENT_ID = "454759368223-lu1gj25efraqtaops85ar172hgdkl6p2.apps.googleusercontent.com"


def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid 10-digit mobile number.",
        )
    return digits


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_response(customer: Customer) -> CustomerTokenResponse:
    token = create_access_token(customer.id, "customer")
    return CustomerTokenResponse(
        access_token=token,
        customer=CustomerOut.model_validate(customer),
    )


def _recent_otp_count(db: Session, phone: str, now: datetime) -> int:
    window_start = now - timedelta(minutes=OTP_RATE_LIMIT_WINDOW_MINUTES)
    # Single indexed count — no per-row loop (api_rules §3).
    return db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.created_at >= window_start,
            OtpCode.expires_at > now,
        )
    ) or 0


def _consume_valid_otp(db: Session, phone: str, purpose: str, code: str, now: datetime) -> None:
    """Raise 401 unless `code` matches the latest unconsumed OTP for phone/purpose."""
    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > now,
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )

    demo_ok = (not IS_PRODUCTION) and code == DEMO_OTP_CODE
    code_ok = bool(otp) and otp.code == code and otp.attempt_count < OTP_MAX_ATTEMPTS

    if not demo_ok and not code_ok:
        if otp:
            otp.attempt_count += 1
            db.commit()
            if otp.attempt_count >= OTP_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="OTP locked after too many attempts. Request a new code.",
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP.",
        )

    if otp and (code_ok or demo_ok):
        otp.consumed_at = now
        db.flush()


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(payload: OtpRequest, db: Session = Depends(get_db)) -> OtpRequestResponse:
    phone = _normalize_phone(payload.phone)
    now = _now()
    window_start = now - timedelta(minutes=OTP_RATE_LIMIT_WINDOW_MINUTES)

    # Single indexed count — no per-row loop (api_rules §3).
    recent_count = db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.created_at >= window_start,
            OtpCode.expires_at > now,
        )
    ) or 0

    if recent_count >= OTP_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Try again later.",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        phone=phone,
        code=code,
        purpose="login",
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
    )
    db.add(otp)
    db.commit()

    # SMS is out of scope for phase 1 — log server-side for local/dev testing.
    if not IS_PRODUCTION:
        logger.info("OTP for phone ending %s: %s", phone[-4:], code)

    return OtpRequestResponse(
        message="OTP sent.",
        expires_in_seconds=OTP_EXPIRY_MINUTES * 60,
    )


@router.post("/otp/verify", response_model=CustomerTokenResponse)
def verify_otp(payload: OtpVerifyRequest, db: Session = Depends(get_db)) -> CustomerTokenResponse:
    phone = _normalize_phone(payload.phone)
    code = payload.code.strip()
    now = _now()

    # Latest unconsumed, unexpired code — one indexed query.
    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > now,
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )

    demo_ok = (not IS_PRODUCTION) and code == DEMO_OTP_CODE
    code_ok = bool(otp) and otp.code == code and otp.attempt_count < OTP_MAX_ATTEMPTS

    if not demo_ok and not code_ok:
        if otp:
            otp.attempt_count += 1
            db.commit()
            if otp.attempt_count >= OTP_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="OTP locked after too many attempts. Request a new code.",
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP.",
        )

    if otp and (code_ok or demo_ok):
        otp.consumed_at = now
        db.flush()

    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if not customer:
        customer = Customer(
            phone=phone,
            name=None,
            email=None,
            is_active=True,
        )
        db.add(customer)
        db.flush()
    elif not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    db.commit()
    db.refresh(customer)
    return _token_response(customer)


@router.post("/register/request-otp", response_model=OtpRequestResponse)
def register_request_otp(
    payload: RegisterRequestOtp, db: Session = Depends(get_db)
) -> OtpRequestResponse:
    """Step 1 of registration: collect name + mobile, send an OTP to verify it."""
    phone = _normalize_phone(payload.phone)
    if not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter your full name.",
        )

    existing = db.scalar(select(Customer).where(Customer.phone == phone))
    if existing and existing.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This mobile number is already registered. Please sign in instead.",
        )

    now = _now()
    if _recent_otp_count(db, phone, now) >= OTP_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Try again later.",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        phone=phone,
        code=code,
        purpose="register",
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
    )
    db.add(otp)
    db.commit()

    if not IS_PRODUCTION:
        logger.info("Register OTP for phone ending %s: %s", phone[-4:], code)

    return OtpRequestResponse(
        message="OTP sent.",
        expires_in_seconds=OTP_EXPIRY_MINUTES * 60,
    )


@router.post("/register/complete", response_model=CustomerTokenResponse)
def register_complete(
    payload: RegisterCompleteRequest, db: Session = Depends(get_db)
) -> CustomerTokenResponse:
    """Step 2 of registration: verify the OTP and set the account password."""
    phone = _normalize_phone(payload.phone)
    name = payload.name.strip()
    code = payload.code.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter your full name.",
        )
    if len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters.",
        )

    now = _now()
    _consume_valid_otp(db, phone, "register", code, now)

    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer and customer.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This mobile number is already registered. Please sign in instead.",
        )

    if customer:
        customer.name = name
        customer.password_hash = hash_password(payload.password)
        customer.is_active = True
    else:
        customer = Customer(
            phone=phone,
            name=name,
            password_hash=hash_password(payload.password),
            is_active=True,
        )
        db.add(customer)
        db.flush()

    db.commit()
    db.refresh(customer)
    return _token_response(customer)


@router.post("/forgot-password/request-otp", response_model=OtpRequestResponse)
def forgot_password_request_otp(
    payload: ForgotPasswordRequestOtp, db: Session = Depends(get_db)
) -> OtpRequestResponse:
    """Step 1 of password reset: send OTP to a registered mobile number."""
    phone = _normalize_phone(payload.phone)
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if not customer or not customer.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No account found with this mobile number. Please register first.",
        )
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    now = _now()
    if _recent_otp_count(db, phone, now) >= OTP_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Try again later.",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        phone=phone,
        code=code,
        purpose="reset_password",
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
    )
    db.add(otp)
    db.commit()

    if not IS_PRODUCTION:
        logger.info("Reset-password OTP for phone ending %s: %s", phone[-4:], code)

    return OtpRequestResponse(
        message="OTP sent.",
        expires_in_seconds=OTP_EXPIRY_MINUTES * 60,
    )


@router.post("/forgot-password/complete", response_model=CustomerTokenResponse)
def forgot_password_complete(
    payload: ForgotPasswordCompleteRequest, db: Session = Depends(get_db)
) -> CustomerTokenResponse:
    """Step 2 of password reset: verify OTP and set a new password."""
    phone = _normalize_phone(payload.phone)
    code = payload.code.strip()
    if len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters.",
        )

    now = _now()
    _consume_valid_otp(db, phone, "reset_password", code, now)

    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if not customer or not customer.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No account found with this mobile number. Please register first.",
        )
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    customer.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(customer)
    return _token_response(customer)


@router.post("/login", response_model=CustomerTokenResponse)
def login(payload: CustomerLoginRequest, db: Session = Depends(get_db)) -> CustomerTokenResponse:
    """Mobile number + password sign-in for customers who completed registration."""
    phone = _normalize_phone(payload.phone)
    customer = db.scalar(select(Customer).where(Customer.phone == phone))

    if not customer or not customer.password_hash or not verify_password(
        payload.password, customer.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile number or password.",
        )
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    return _token_response(customer)


@router.get("/google/mobile-redirect", response_class=HTMLResponse)
def google_mobile_redirect() -> HTMLResponse:
    """Bridge Google implicit OAuth (#id_token) back into the Android app scheme."""
    return HTMLResponse(
        content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Signing in…</title>
  <style>
    body { font-family: system-ui, sans-serif; text-align: center; padding: 48px 16px; color: #1a1a1a; }
  </style>
</head>
<body>
  <p>Completing Google sign-in…</p>
  <script>
    (function () {
      var hash = window.location.hash ? window.location.hash.replace(/^#/, "") : "";
      var params = new URLSearchParams(hash);
      var query = new URLSearchParams(window.location.search);
      var idToken = params.get("id_token") || query.get("id_token");
      var error = params.get("error") || query.get("error");
      var scheme = "com.renown.renown_customer";
      if (error) {
        window.location.replace(scheme + "://oauth?error=" + encodeURIComponent(error));
        return;
      }
      if (!idToken) {
        window.location.replace(scheme + "://oauth?error=" + encodeURIComponent("missing_token"));
        return;
      }
      window.location.replace(scheme + "://oauth?id_token=" + encodeURIComponent(idToken));
    })();
  </script>
</body>
</html>""",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/google", response_model=CustomerTokenResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> CustomerTokenResponse:
    """Verify a Google ID token and issue a customer JWT."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        info = google_id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
        email = info.get("email")
        google_sub = info.get("sub")
        name = info.get("name") or (email.split("@")[0].title() if email else "Customer")
        if not email or not google_sub:
            raise ValueError("Email or sub not present in Google token")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google token: {exc}",
        ) from exc

    customer = db.scalar(select(Customer).where(Customer.google_sub == google_sub))
    if not customer:
        customer = db.scalar(select(Customer).where(Customer.email == email))

    if customer is None:
        customer = Customer(
            email=email,
            name=name,
            google_sub=google_sub,
            phone=None,
            is_active=True,
        )
        db.add(customer)
        db.flush()
    else:
        if not customer.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is inactive.",
            )
        customer.email = email
        customer.name = name or customer.name
        customer.google_sub = google_sub

    db.commit()
    db.refresh(customer)
    return _token_response(customer)
