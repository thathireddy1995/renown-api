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
DEMO_OTP_CODE = "123456"
OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_WINDOW_MINUTES = 10
OTP_RATE_LIMIT_MAX = 5
OTP_MAX_ATTEMPTS = 5

# MSG91 WhatsApp Authentication OTP (meta-apis/login_code.py).
# Override via env / Lambda parameter-overrides — do not rely on defaults in prod.
MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY", "")
MSG91_WA_INTEGRATED_NUMBER = os.getenv("MSG91_WA_NUMBER", "919642512952")
MSG91_WA_TEMPLATE_NAME = os.getenv("MSG91_WA_TEMPLATE", "verify_user_v1")
MSG91_WA_TEMPLATE_LANG = os.getenv("MSG91_WA_LANG", "en_US")
MSG91_WA_NAMESPACE = os.getenv("MSG91_WA_NAMESPACE", "").strip()

# Razorpay sandbox keys (test mode). Override via env vars for production.
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_TFQQhSY0gwUMhs")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "EGGkPibPOmeLQN6fRTUpK7Qi")

# Shiprocket API user (Settings → API). Never commit real values to git.
SHIPROCKET_EMAIL = os.getenv("SHIPROCKET_EMAIL", "")
SHIPROCKET_PASSWORD = os.getenv("SHIPROCKET_PASSWORD", "")
