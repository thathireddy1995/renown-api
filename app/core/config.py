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
