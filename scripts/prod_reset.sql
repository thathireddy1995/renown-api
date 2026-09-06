-- prod_reset.sql
-- Wipe transactional / test data for go-live. KEEP storefront catalog + settings.
--
-- KEEP (never truncate):
--   products, product_variants, product_images
--   categories, brands, collections
--   lens_types, frame_types, colors, sizes, attributes, attribute_values
--   offers, coupons
--   home_banners, mobile_banners
--   warehouses (Tirupati only after cleanup), stores (Tirupati STORE-1 only)
--   warehouse_inventory / store_inventory for kept locations
--   system_settings, schema_migrations, suppliers
--   doctors (repointed), single admin user 7013332720
--
-- Applied by: python -m scripts.run_prod_reset --yes

TRUNCATE TABLE
  product_review_images,
  product_reviews,
  coupon_redemptions,
  order_items,
  packs,
  dispatch_order_items,
  dispatch_orders,
  pick_list_items,
  pick_lists,
  stock_allocations,
  inventory_audit_items,
  inventory_audits,
  grn_items,
  grn,
  purchase_orders,
  transfer_requests,
  stock_transfer_items,
  stock_transfers,
  store_order_items,
  store_orders,
  cart_items,
  wishlist_items,
  compare_items,
  addresses,
  customer_prescriptions,
  prescriptions,
  appointments,
  orders,
  customers,
  otp_codes,
  web_analytics_events,
  import_jobs,
  employees
RESTART IDENTITY CASCADE;

UPDATE home_banners SET created_by = NULL, updated_by = NULL;

UPDATE mobile_banners SET created_by = NULL, updated_by = NULL;

UPDATE offers SET created_by = NULL, updated_by = NULL;

UPDATE coupons SET created_by = NULL, updated_by = NULL;

UPDATE doctors SET store_id = NULL WHERE store_id IS DISTINCT FROM 13;

UPDATE users SET store_id = NULL, warehouse_id = NULL;

DELETE FROM stores WHERE id <> 13;

DELETE FROM warehouses WHERE id <> 9;

UPDATE stores
SET warehouse_id = 9,
    city = 'Tirupati',
    status = 'Open'
WHERE id = 13;

DELETE FROM users WHERE phone IS DISTINCT FROM '7013332720';

UPDATE users
SET role = 'admin',
    is_active = TRUE,
    store_id = NULL,
    warehouse_id = NULL,
    name = COALESCE(NULLIF(TRIM(name), ''), 'Admin'),
    updated_at = NOW()
WHERE phone = '7013332720';
