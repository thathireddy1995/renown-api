import os

from dotenv import load_dotenv

# In Lambda, real env vars are set on the function config (template.yaml) and
# this is a no-op. Locally, it loads renown-api/.env (gitignored).
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to renown-api/.env for local dev, "
        "or as a Lambda environment variable in production."
    )

JWT_SECRET = os.getenv("JWT_SECRET")

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Add it to renown-api/.env for local dev, "
        "or as a Lambda environment variable in production."
    )

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))

CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    # Allow the bare production domain (customer portal) as well as any single
    # subdomain (admin., staff., www., etc.) — a leading-dot-only regex here
    # previously rejected the apex domain and broke prod sign-in/API calls.
    r"^https?://localhost(:\d+)?$|^https://([a-z0-9-]+\.)?renowneyewear\.com$",
)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"
OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_WINDOW_MINUTES = 10
OTP_RATE_LIMIT_MAX = 5
OTP_MAX_ATTEMPTS = 5

# MSG91 WhatsApp Authentication OTP (meta-apis/login_code.py).
# Hardcoded for now — move to secrets / env later.
# Use `or` so empty Lambda env vars don't wipe the defaults.
MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY") or "554114Avcg6BwNFF6a65c35aP1"
MSG91_WA_INTEGRATED_NUMBER = os.getenv("MSG91_WA_NUMBER") or "919642512952"
MSG91_WA_TEMPLATE_NAME = os.getenv("MSG91_WA_TEMPLATE") or "verify_user_v1"
MSG91_WA_TEMPLATE_LANG = os.getenv("MSG91_WA_LANG") or "en_US"
MSG91_WA_NAMESPACE = (os.getenv("MSG91_WA_NAMESPACE") or "").strip()

# Razorpay Standard Checkout. Override via env / SAM parameters.
# Prefer live keys in production (.env / deploy); never expose KEY_SECRET to the frontend.
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID") or "rzp_live_TYZikwbbGsP7pE"
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET") or "dmWAny26145LqUR6KXKDhpOJ"

# Shiprocket API user (Settings → API). Never commit real values to git.
SHIPROCKET_EMAIL = os.getenv("SHIPROCKET_EMAIL", "")
SHIPROCKET_PASSWORD = os.getenv("SHIPROCKET_PASSWORD", "")
# Pickup nickname in Shiprocket (Settings → Pickup Address). Auto-created if missing.
SHIPROCKET_PICKUP_LOCATION = (os.getenv("SHIPROCKET_PICKUP_LOCATION") or "Primary").strip() or "Primary"
SHIPROCKET_DEFAULT_WEIGHT_KG = float(os.getenv("SHIPROCKET_DEFAULT_WEIGHT_KG") or "0.5")
SHIPROCKET_DEFAULT_LENGTH_CM = float(os.getenv("SHIPROCKET_DEFAULT_LENGTH_CM") or "15")
SHIPROCKET_DEFAULT_BREADTH_CM = float(os.getenv("SHIPROCKET_DEFAULT_BREADTH_CM") or "10")
SHIPROCKET_DEFAULT_HEIGHT_CM = float(os.getenv("SHIPROCKET_DEFAULT_HEIGHT_CM") or "8")

# Public product images — files live in S3; Postgres only stores the https URL.
S3_PUBLIC_BUCKET = os.getenv("S3_PUBLIC_BUCKET", "renown-public")
S3_PUBLIC_REGION = os.getenv("S3_PUBLIC_REGION", "ap-south-2")
S3_PUBLIC_BASE_URL = (
    os.getenv("S3_PUBLIC_BASE_URL")
    or f"https://{S3_PUBLIC_BUCKET}.s3.{S3_PUBLIC_REGION}.amazonaws.com"
)
S3_PRESIGN_EXPIRES_SECONDS = int(os.getenv("S3_PRESIGN_EXPIRES_SECONDS", "600"))

AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-south-2"
ORDER_NOTIFY_QUEUE_URL = (
    os.getenv("ORDER_NOTIFY_QUEUE_URL")
    or "https://sqs.ap-south-2.amazonaws.com/021859651726/optimus-order-notify"
)
