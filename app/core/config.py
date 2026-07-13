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
    r"^https?://localhost(:\d+)?$|^https://.*\.renowneyewear\.com$",
)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"
DEMO_OTP_CODE = "123456"
OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_WINDOW_MINUTES = 10
OTP_RATE_LIMIT_MAX = 5
OTP_MAX_ATTEMPTS = 5
