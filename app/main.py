from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from mangum import Mangum

from app.core.config import CORS_ORIGIN_REGEX
from app.routers import admin_auth, customer_auth, staff_auth

app = FastAPI(
    title="Renown Opticals API",
    description="Backend API for the Renown opticals ecommerce platform",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_auth.router)
app.include_router(staff_auth.router)
app.include_router(customer_auth.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
