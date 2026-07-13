from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.core.config import CORS_ORIGIN_REGEX
from app.routers import (
    admin_auth,
    admin_catalog,
    admin_catalog_variants,
    admin_opticals,
    admin_taxonomy,
    customer_auth,
    customer_cart,
    customer_catalog,
    customer_compare,
    customer_products,
    customer_wishlist,
    staff_auth,
)

app = FastAPI(
    title="Renown Opticals API",
    description="Backend API for the Renown opticals ecommerce platform",
    version="0.1.0",
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
app.include_router(admin_catalog.router)
app.include_router(admin_catalog_variants.router)
app.include_router(admin_taxonomy.router)
app.include_router(admin_opticals.router)
app.include_router(customer_products.router)
app.include_router(customer_catalog.router)
app.include_router(customer_cart.router)
app.include_router(customer_wishlist.router)
app.include_router(customer_compare.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
