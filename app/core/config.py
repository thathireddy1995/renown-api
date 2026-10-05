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
# Customer storefront only. Staff and admin stay on JWT_EXPIRE_MINUTES.
CUSTOMER_JWT_EXPIRE_MINUTES = int(os.getenv("CUSTOMER_JWT_EXPIRE_MINUTES", str(45 * 24 * 60)))

CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    # Allow the bare production domain (customer portal) as well as any single
    # subdomain (admin., staff., www., etc.) — a leading-dot-only regex here
    # previously rejected the apex domain and broke prod sign-in/API calls.
    # Locally allow both localhost and 127.0.0.1 (Vite may bind either).
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://([a-z0-9-]+\.)?renowneyewear\.com$",
)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"
OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_WINDOW_MINUTES = 10
OTP_RATE_LIMIT_MAX = 5
OTP_MAX_ATTEMPTS = 5

# Meta WhatsApp Cloud API — Authentication template OTP (meta-apis/renown/check_and_send.py).
# The access token is a secret: set it in .env / deploy, never in source.
# Use `or` so empty Lambda env vars don't wipe the defaults.
WHATSAPP_ACCESS_TOKEN = (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()
WHATSAPP_PHONE_NUMBER_ID = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "1328705783660234").strip()
WHATSAPP_OTP_TEMPLATE = (os.getenv("WHATSAPP_OTP_TEMPLATE") or "verify_v1").strip()
WHATSAPP_OTP_LANG = (os.getenv("WHATSAPP_OTP_LANG") or "en_US").strip()
WHATSAPP_GRAPH_VERSION = (os.getenv("WHATSAPP_GRAPH_VERSION") or "v25.0").strip()

# Razorpay Standard Checkout. Override via env / SAM parameters.
# Prefer live keys in production (.env / deploy); never expose KEY_SECRET to the frontend.
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID") or "rzp_live_TYZikwbbGsP7pE"
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET") or "dmWAny26145LqUR6KXKDhpOJ"

# Shiprocket API user (Settings → API). Never commit real values to git.
SHIPROCKET_EMAIL = os.getenv("SHIPROCKET_EMAIL", "")
SHIPROCKET_PASSWORD = os.getenv("SHIPROCKET_PASSWORD", "")
# Pickup nickname in Shiprocket (Settings → Pickup Address). Auto-created if missing.
SHIPROCKET_PICKUP_LOCATION = (os.getenv("SHIPROCKET_PICKUP_LOCATION") or "Store").strip() or "Store"
SHIPROCKET_DEFAULT_WEIGHT_KG = float(os.getenv("SHIPROCKET_DEFAULT_WEIGHT_KG") or "0.5")
SHIPROCKET_DEFAULT_LENGTH_CM = float(os.getenv("SHIPROCKET_DEFAULT_LENGTH_CM") or "15")
SHIPROCKET_DEFAULT_BREADTH_CM = float(os.getenv("SHIPROCKET_DEFAULT_BREADTH_CM") or "10")
SHIPROCKET_DEFAULT_HEIGHT_CM = float(os.getenv("SHIPROCKET_DEFAULT_HEIGHT_CM") or "8")
# Shared secret for the courier tracking webhook. Shiprocket sends it back as
# the x-api-key header (Settings → API → Webhooks). Without it the endpoint
# refuses every call, since it writes order status from an unauthenticated
# caller otherwise.
SHIPROCKET_WEBHOOK_TOKEN = (os.getenv("SHIPROCKET_WEBHOOK_TOKEN") or "").strip()

# Public product images — files live in S3; Postgres only stores the https URL.
S3_PUBLIC_BUCKET = os.getenv("S3_PUBLIC_BUCKET", "renown-public")
S3_PUBLIC_REGION = os.getenv("S3_PUBLIC_REGION", "ap-south-2")
S3_PUBLIC_BASE_URL = (
    os.getenv("S3_PUBLIC_BASE_URL")
    or f"https://{S3_PUBLIC_BUCKET}.s3.{S3_PUBLIC_REGION}.amazonaws.com"
)
S3_PRESIGN_EXPIRES_SECONDS = int(os.getenv("S3_PRESIGN_EXPIRES_SECONDS", "600"))

# Firebase service account (project renown-apk) for FCM HTTP v1 pushes.
# Either a path to the JSON key file, or the raw JSON in the env var (Lambda).
FIREBASE_SERVICE_ACCOUNT_FILE = (os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE") or "").strip()
FIREBASE_SERVICE_ACCOUNT_JSON = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or "").strip()

AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-south-2"
ORDER_NOTIFY_QUEUE_URL = (
    os.getenv("ORDER_NOTIFY_QUEUE_URL")
    or "https://sqs.ap-south-2.amazonaws.com/021859651726/optimus-order-notify"
)
