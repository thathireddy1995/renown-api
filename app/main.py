from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.core.config import CORS_ORIGIN_REGEX
from app.routers import (
    admin_auth,
    admin_catalog,
    admin_catalog_variants,
    admin_customers,
    admin_dashboard,
    admin_employees,
    admin_opticals,
    admin_orders,
    admin_reports,
    admin_stock_allocation,
    admin_store_orders,
    admin_stores,
    admin_taxonomy,
    admin_transfer_requests,
    admin_warehouse_transfers,
    admin_warehouses,
    customer_addresses,
    customer_appointments,
    customer_auth,
    customer_cart,
    customer_catalog,
    customer_compare,
    customer_orders,
    customer_products,
    customer_wishlist,
    staff_auth,
    staff_store_appointments,
    staff_store_orders,
    staff_store_pos,
    staff_store_prescriptions,
    staff_store_reports,
    staff_store_staff,
    staff_warehouse_dispatch,
    staff_warehouse_packing,
    staff_warehouse_picking,
    staff_warehouse_receiving,
    staff_warehouse_reports,
    staff_warehouse_suppliers,
    staff_warehouse_transfers,
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
app.include_router(staff_warehouse_suppliers.router)
app.include_router(staff_warehouse_receiving.router)
app.include_router(staff_warehouse_picking.router)
app.include_router(staff_warehouse_packing.router)
app.include_router(staff_warehouse_dispatch.router)
app.include_router(staff_warehouse_transfers.router)
app.include_router(staff_store_pos.router)
app.include_router(staff_store_orders.router)
app.include_router(staff_store_appointments.router)
app.include_router(staff_store_prescriptions.router)
app.include_router(staff_store_staff.router)
app.include_router(staff_store_reports.reports_router)
app.include_router(staff_store_reports.dashboard_router)
app.include_router(staff_warehouse_reports.reports_router)
app.include_router(staff_warehouse_reports.dashboard_router)
app.include_router(customer_auth.router)
app.include_router(customer_appointments.router)
app.include_router(admin_catalog.router)
app.include_router(admin_catalog_variants.router)
app.include_router(admin_taxonomy.router)
app.include_router(admin_opticals.router)
app.include_router(admin_orders.router)
app.include_router(admin_customers.router)
app.include_router(admin_employees.router)
app.include_router(admin_reports.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_warehouses.router)
app.include_router(admin_stores.router)
app.include_router(admin_warehouse_transfers.router)
app.include_router(admin_transfer_requests.router)
app.include_router(admin_stock_allocation.router)
app.include_router(admin_store_orders.router)
app.include_router(customer_products.router)
app.include_router(customer_catalog.router)
app.include_router(customer_cart.router)
app.include_router(customer_wishlist.router)
app.include_router(customer_compare.router)
app.include_router(customer_addresses.router)
app.include_router(customer_orders.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
