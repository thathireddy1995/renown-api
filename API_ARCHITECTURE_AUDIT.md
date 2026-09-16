# Renown API architecture audit

Scope: `renown-api` production request paths, with emphasis on SQLAlchemy query behavior and AWS Lambda/API Gateway design.

Date: 2026-09-05

This is a static code audit. “Confirmed” means the pattern is directly visible in code. Items marked “risk” should be verified with production metrics before sizing infrastructure.

## Executive summary

The API has several good foundations: one module-level SQLAlchemy engine, a small connection pool suitable for a Lambda container, eager loading on the main product/order lists, batched lens-fit loading, and a reused SQS client.

The main issues are:

1. Secrets and sensitive artifacts are committed / packaged into the Lambda deploy bundle.
2. Razorpay payment verify can create duplicate orders under retry.
3. Customer checkout performs multiple blocking Shiprocket calls inside the API Gateway request.
4. Several warehouse write paths issue one or more SQL queries per line item.
5. Lambda can scale without a concurrency guard while every warm container can retain a database connection.
6. The Lambda package is oversized (~131 MB) with duplicate/unneeded runtime dependencies.

## Prioritized findings

### F1 — Critical — Secrets and sensitive artifacts are committed / packaged

**Status:** Confirmed

**Place**

- `template.yaml:23-49`, `template.yaml:110-117`
- `app/core/config.py:46-54` (MSG91 / Razorpay fallback defaults)
- `deploy.sh:7-9` (long-lived AWS access keys)
- `backups/renown-production-20260819-143112.dump` (production DB dump)
- Missing `.samignore` with `CodeUri: .` (`template.yaml:99`)
- Built artifact currently ~131 MB under `.aws-sam/build/FastApiFunction`

`RazorpayKeySecret`, `ShiprocketPassword`, and `Msg91AuthKey` have concrete defaults in source control. `NoEcho` only hides values in CloudFormation output; it does not protect values committed in Git. The SAM build can also package `deploy.sh`, dumps, migrations, and other non-runtime files into the Lambda zip.

**Impact**

- Credential disclosure and unauthorized payment, shipping, messaging, or AWS API use.
- Anyone with Lambda artifact / deploy-bucket read access can obtain secrets and a DB dump.
- Rotating only the current file is insufficient because Git history retains old values.

**Proposed fix**

1. Rotate every exposed credential and DB password immediately.
2. Remove secret defaults from `template.yaml` and Python fallbacks; require secret identifiers instead.
3. Store secrets in AWS Secrets Manager or SSM Parameter Store and grant the Lambda role access only to the required secret ARNs.
4. Add `.samignore` excluding `backups/`, `deploy.sh`, `migrations/`, `scripts/`, `.env*`, dumps, and local tooling.
5. Stop committing AWS keys in `deploy.sh`; use SSO/OIDC/role-based deploy credentials.
6. Add secret scanning (for example, Gitleaks) to pre-commit and CI.

Example target shape:

```yaml
Parameters:
  ShiprocketSecretArn:
    Type: String

Environment:
  Variables:
    SHIPROCKET_SECRET_ARN: !Ref ShiprocketSecretArn

Policies:
  - AWSSecretsManagerGetSecretValuePolicy:
      SecretArn: !Ref ShiprocketSecretArn
```

### F1b — Critical — Payment verify lacks idempotency

**Status:** Confirmed

**Place**

- `app/routers/customer_payments.py:88-141`
- `app/schemas.py:616-617` (`razorpay_order_id` / `razorpay_payment_id` nullable, not unique)

`verify_payment()` verifies the Razorpay signature, then always creates a new order. There is no lookup for an existing order by `razorpay_payment_id`, and the columns are not unique-constrained.

**Impact**

- Concurrent retries (double-click, mobile retry, gateway retry) can create multiple orders for one captured payment.
- Cart-empty checks only protect late retries, not parallel requests.

**Proposed fix**

1. At the start of `verify_payment()`, look up an existing order by `razorpay_payment_id` (or `razorpay_order_id`) and return it if found.
2. Add a unique constraint/migration on `razorpay_payment_id`.
3. Wrap verify + cart lock in one transaction (`SELECT … FOR UPDATE` on cart lines or customer row).
4. Prefer Razorpay webhooks as the durable fulfillment trigger for paid orders.

### F2 — High — Lambda timeout is incompatible with the HTTP API timeout

**Status:** Confirmed

**Place**

- `template.yaml:72-75`
- `template.yaml:151-164`

The Lambda timeout is 900 seconds, while API Gateway stops waiting after 29 seconds. A handler can continue consuming Lambda duration after the client has already received a gateway timeout.

**Impact**

- Wasted Lambda cost and capacity.
- Ambiguous client outcomes and unsafe retries.
- Slow external dependencies can occupy executions for minutes.

**Proposed fix**

- Set the synchronous API Lambda timeout to approximately 25–28 seconds.
- Give outbound HTTP calls shorter connect/read timeouts within that budget.
- Move long-running fulfillment work to asynchronous workers with their own timeout.
- Use separate Lambda functions for HTTP and background jobs instead of one 900-second function.

### F3 — High — Checkout synchronously performs Shiprocket fulfillment

**Status:** Confirmed

**Place**

- `app/routers/customer_orders.py:368-384`
- `app/routers/customer_payments.py:117-141`
- `app/core/shiprocket_fulfill.py:172-226`
- `app/core/shiprocket.py:35-45, 70-91`

After the order transaction commits, checkout can call Shiprocket to list/create a pickup location, create an order, and assign an AWB. Each HTTP request has a 30-second timeout and a 401/403 can trigger another request. The customer request therefore can exceed API Gateway’s 29-second limit even though the order was successfully created.

**Impact**

- Customer sees a failed/timeout checkout although the order exists.
- Client retries can create confusing duplicate workflows unless every checkout path is fully idempotent.
- Shiprocket latency directly degrades checkout latency and Lambda concurrency.

**Proposed fix**

Use a transactional outbox or an SQS fulfillment queue:

1. In the same database transaction as the order, insert an `order_fulfillment_jobs` row with a unique key such as `order_id + job_type`.
2. Return the order immediately.
3. Publish pending jobs to SQS, or use a database outbox relay.
4. Let a dedicated Lambda create the Shiprocket order/AWB.
5. Make the worker idempotent, apply bounded retries, and configure a DLQ.
6. Expose fulfillment state (`pending`, `booked`, `failed`) to admin/customer UIs.

The existing order-notification SQS pattern is a useful starting point, but reliable fulfillment needs an outbox so a DB commit and queue publish cannot diverge.

### F4 — High — Warehouse dispatch performs per-line validation and inventory queries

**Status:** Confirmed N+1 write pattern

**Place**

- `app/routers/staff_warehouse_dispatch.py:126-147`
- `app/routers/staff_warehouse_dispatch.py:250-284`

For `N` dispatch lines, the endpoint performs:

- `N` `db.get(ProductVariant, id)` validations.
- `N` inventory `SELECT` queries through `_decrement_inventory`.

This is approximately `2N` queries, excluding the surrounding request work. The read-then-write sequence also allows concurrent requests to pass the same stock check.

**Proposed fix**

1. Deduplicate variant IDs.
2. Load all variants in one `WHERE id IN (...)` query.
3. Load all warehouse inventory rows in one query, ideally with `SELECT ... FOR UPDATE`.
4. Validate missing variants and insufficient quantities in memory.
5. Apply updates in one transaction.

For stronger concurrency safety, use conditional atomic updates:

```sql
UPDATE warehouse_inventory
SET on_hand = on_hand - :qty
WHERE warehouse_id = :warehouse_id
  AND variant_id = :variant_id
  AND on_hand >= :qty;
```

Check affected-row counts and roll back the whole dispatch if any line fails.

### F5 — High — GRN receiving validates and increments inventory per line

**Status:** Confirmed N+1 write pattern

**Place**

- `app/routers/staff_warehouse_receiving.py:50-72`
- `app/routers/staff_warehouse_receiving.py:193-229`

For `N` GRN lines, the endpoint performs `N` variant lookups and up to `N` inventory lookups. This becomes roughly `2N` SQL queries.

**Proposed fix**

- Bulk-load variants with one `IN` query.
- Bulk-load existing inventory rows for `(warehouse_id, variant_id)` in one query.
- Use PostgreSQL `INSERT ... ON CONFLICT (warehouse_id, variant_id) DO UPDATE SET on_hand = warehouse_inventory.on_hand + EXCLUDED.on_hand`.
- Add all GRN lines and inventory changes in one transaction.

This removes the query loop and makes concurrent receipts additive instead of last-write-prone.

### F6 — High — Stock transfer creation/completion queries per item

**Status:** Confirmed N+1 write pattern

**Place**

- `app/core/stock_transfers.py:268-274`
- `app/core/stock_transfers.py:320-358`
- `app/core/stock_transfers.py:379-412`

Creation validates each variant separately. Completion calls `_wh_inv` or `_store_inv` for both source and destination inside the line loop, resulting in up to `2N` inventory reads plus the creation-time `N` validations.

**Proposed fix**

- Normalize and deduplicate line items before querying.
- Bulk-load all variant IDs.
- Bulk-load source and destination inventory rows using two `IN` queries (or one unioned query).
- Lock source rows with `FOR UPDATE`.
- Upsert missing destination rows in bulk.
- Validate all source quantities before mutating any row.
- Keep the transfer status change and inventory movement in the same transaction.

### F7 — Medium — Checkout resolves default variants per cart line, sometimes twice

**Status:** Confirmed N+1 write pattern for cart lines without `variant_id`

**Place**

- `app/core/order_service.py:159-184`
- `app/core/order_service.py:218-227`
- `app/core/order_service.py:284-301`

`_resolve_line_variant_id` executes one or two queries for each cart line lacking a variant. `create_order_record` calls it while building web order items; click-and-collect then calls it again while building mirrored store-order items.

**Impact**

For `N` unresolved lines, checkout can execute up to `4N` fallback queries. It also risks resolving a different “first” variant if catalog data changes between calls.

**Proposed fix**

- Resolve all missing variants once before creating either order.
- Query the first live variant for all product IDs using PostgreSQL `DISTINCT ON (product_id)` or `row_number() over (partition by product_id order by id)`.
- Store the resolved ID in a normalized checkout-line structure reused by both `OrderItem` and `StoreOrderItem`.
- Prefer requiring a concrete variant in the cart when a product has variants.

### F8 — Medium — Legacy pickup-order fallback can query once per listed order

**Status:** Confirmed conditional N+1

**Place**

- `app/routers/customer_orders.py:160-175`
- `app/routers/customer_orders.py:220-246`

The primary `pickup_store` relationship is eagerly loaded. However, when older orders have no usable `pickup_store_id`, `_pickup_out` queries `StoreOrder` (and potentially `Store`) for each order during list serialization.

**Proposed fix**

- Backfill `orders.pickup_store_id` for legacy pickup orders.
- For compatibility during migration, batch-load all matching `StoreOrder` rows for the page by `order_number IN (...)`, eager-load their stores, and pass a lookup map into `_order_out`.
- Remove the per-row database fallback after the backfill is verified.

### F9 — Medium risk — Lambda concurrency is not bounded against database capacity

**Status:** Infrastructure risk confirmed by configuration; production sizing requires metrics

**Place**

- `app/database.py:28-45`
- `template.yaml:92-138`

The module-level engine and `pool_size=1, max_overflow=0` are appropriate for a single warm Lambda container. However, the function has no reserved concurrency. A traffic spike can create many containers, each retaining one PostgreSQL/PgBouncer connection.

**Proposed fix**

- Calculate a safe reserved concurrency from PgBouncer/database limits, leaving capacity for admin jobs and migrations.
- Set `ReservedConcurrentExecutions` on `FastApiFunction`.
- Alarm on Lambda concurrency/throttles and PgBouncer client/server connection saturation.
- If concurrency grows substantially, evaluate RDS Proxy only if the database moves to RDS/Aurora; for the current external PostgreSQL deployment, keep PgBouncer and enforce a concurrency budget.

### F10 — Medium — External API failures are not handled by an idempotent job model

**Status:** Confirmed design gap

**Place**

- `app/core/shiprocket_fulfill.py:172-226`
- `app/core/warehouse_deliveries.py:242-244`

Shiprocket creation and pickup scheduling are best-effort calls after database commits. Failures are logged, but there is no durable retry state, retry schedule, or dead-letter path in this API.

**Proposed fix**

- Persist fulfillment jobs and attempts.
- Give every action an idempotency key.
- Retry transient failures with exponential backoff and jitter.
- Send terminal failures to a DLQ and expose them to admin operations.
- Never rely only on CloudWatch log text as the recovery mechanism.

### F11 — Low — S3 client is recreated for each presign/delete operation

**Status:** Confirmed

**Place**

- `app/core/s3_images.py:90-106`

`_s3()` constructs a new boto3 client each time instead of caching it for the warm Lambda container. This adds repeated client/config initialization.

**Proposed fix**

Create the S3 client once at module scope or use a lazy cached singleton, matching `telegram_notify._sqs_client`.

### F12 — Low — Lambda deployment package contains duplicate/unneeded dependencies

**Status:** Confirmed

**Place**

- `requirements.txt:3-6, 13`
- `.aws-sam/build/FastApiFunction` ≈ **131 MB** (measured locally)
- Missing `.samignore` (also covered under F1)

The package includes `uvicorn[standard]`, both psycopg v3 and psycopg2, and boto3. Mangum does not need Uvicorn in Lambda, the application should use one PostgreSQL driver, and Lambda already supplies boto3 (pinning a packaged boto3 is valid only when deliberately controlling SDK version compatibility).

**Impact**

- Larger deployment artifact and slower cold-start import/decompression.
- More dependency and CVE surface.

**Proposed fix**

- Move local-only Uvicorn into `requirements-dev.txt`.
- Keep only the PostgreSQL driver used by `DATABASE_URL`.
- Either rely on the Lambda runtime boto3 or deliberately pin/package boto3 and botocore together.
- Add `.samignore` and measure `Init Duration` before/after.

### F13 — Medium — Observability is too weak for Lambda performance diagnosis

**Status:** Confirmed configuration gap

**Place**

- `template.yaml:84-89, 168-171`
- `app/main.py:74-166`

There is a Lambda log group, but no API Gateway access-log configuration, Lambda tracing, structured request correlation, or alarms in the SAM stack. `/health` is a shallow liveness check and does not prove DB/queue readiness.

**Proposed fix**

- Enable HTTP API access logs with request ID, route, status, response latency, and integration latency.
- Enable Lambda X-Ray tracing or OpenTelemetry.
- Add structured JSON logs carrying API Gateway request ID and order/job identifiers.
- Add alarms for 5xx, p95/p99 latency, API integration timeout, Lambda errors/throttles/duration, SQS age/DLQ depth, and PgBouncer saturation.
- Split `/health` (liveness) from `/ready` (DB + critical dependency probe) used only by internal monitors.
- Add per-route SQL query-count/latency instrumentation in non-production tests.

### F14 — Medium — Admin bulk product import looks up brands/categories one name at a time

**Status:** Confirmed N+1 write pattern

**Place**

- `app/routers/admin_operations.py:172-173, 188-189`
- `app/core/catalog_lookups.py:28-35` (`brand_id_for` / `category_id_for`)
- Contrast: `collection_ids_for` (`catalog_lookups.py:50`) already batches correctly

Comment nearby implies “batch”, but maps are built as `{n: brand_id_for(db, n) for n in brand_names}` (and again after `flush()`). Unique brand/category names each cost a separate query.

**Proposed fix**

Add `brand_ids_for(db, names)` / `category_ids_for(db, names)` mirroring `collection_ids_for` — one `WHERE lower(name) IN (...)` per table — and reuse the maps for both pre- and post-flush resolution.

### F15 — Medium — Many paginated endpoints still use separate COUNT + LIST queries

**Status:** Confirmed latency multiplier

**Place (examples)**

- `app/routers/customer_products.py` (`list_products`)
- `app/routers/customer_orders.py` (`list_orders`)
- `app/routers/store_app.py` (`stock`, `list_orders`)
- `app/routers/staff_store_inventory.py`, `admin_warehouses.py` inventory lists

Contrast already-good pattern: `admin_orders.py`, `admin_users.py`, `admin_catalog.py`, `admin_taxonomy.py` use `func.count().over()` so list + total share one round-trip.

**Impact**

On a remote Postgres (~90 ms RTT cited in admin dashboard comments), every page costs two serial round-trips instead of one.

**Proposed fix**

Standardize paginated list endpoints on a window `total_count` column (or a single CTE) so `LIMIT/OFFSET` and total come from one execute.

### F16 — Medium — Offer pricing loads all active offers for every product/cart/POS pricing call

**Status:** Confirmed scalability smell

**Place**

- `app/core/offer_pricing.py` (`winning_offers_for`)
- Callers: `customer_products.py`, cart load, `staff_store_pos.py`
- Contrast: `customer_home.py` already picks winners in SQL

Fetches every non-inactive in-window offer, then nested-loops products × offers in Python. Fine at small offer counts; degrades as the offer table grows.

**Proposed fix**

Push applicability filters into SQL (brand/category/gender/product id), or cache the active-offer set per warm container with a short TTL. Prefer the home-page SQL winner pattern for list endpoints.

### F17 — Medium — Clinical store resolution loads the full store table

**Status:** Confirmed

**Place**

- `app/core/clinical.py:141-158` (`resolve_store`)
- Used from appointment booking (`customer_appointments.py`, `staff_store_appointments.py`)

When matching by label, loads all stores ordered by id and scans in Python (including city alias logic).

**Proposed fix**

Replace with an indexed SQL filter (`lower(city) = :needle OR lower(name) ILIKE :like LIMIT 1`), optionally materializing `CITY_ALIASES` as a small lookup rather than an in-memory full scan.

### F18 — Medium — Blocking OTP / Shiprocket work holds the request (and often the DB session) open

**Status:** Confirmed design smell

**Place**

- `app/core/whatsapp_otp.py:107` (`requests.post(..., timeout=30)`)
- Checkout Shiprocket path (see F3)
- Warehouse fulfill: DB commit then external pickup (`warehouse_deliveries.py:242-244`)

Login/OTP and checkout paths wait synchronously on third-party HTTP. Combined with F2’s 900s Lambda timeout, a slow vendor can occupy concurrency while the client already timed out at API Gateway.

**Proposed fix**

- Cap third-party timeouts to a few seconds inside the HTTP budget.
- Prefer async OTP send with a “code accepted, delivery pending” UX where product allows it.
- Never leave a SQLAlchemy session open across outbound HTTP; commit/close first, then call vendors, or use an outbox worker (F3/F10).

### F19 — Low — Number / SKU allocation probes in a collision loop

**Status:** Confirmed rare-path cost

**Place**

- `app/core/catalog_lookups.py` (`next_product_sku`)
- `order_service.next_order_number`, `warehouse_deliveries.next_do_number`, `stock_transfers.next_transfer_number`, GRN/POS number helpers

Up to ~25 scalar existence checks under collision; `next_product_sku` can also probe each gap in sequence.

**Proposed fix**

Prefer `max + 1` (or a counter table / advisory lock), unique DB constraints, and retry only on `IntegrityError`. Avoid per-candidate `SELECT` loops in the happy path.

### F20 — Low — `persist_stock_transfer` commits inside the helper

**Status:** Confirmed transaction-boundary smell

**Place**

- `app/core/stock_transfers.py` (`persist_stock_transfer` ~line 298)

Callers cannot wrap creation with related side effects in one outer transaction.

**Proposed fix**

`flush()` in the helper; let the router commit, or accept an explicit `commit: bool = True` parameter for backward compatibility.

## Patterns checked and found sound

- `app/database.py` creates the SQLAlchemy engine once at module import, so warm Lambda invocations reuse it.
- `pool_size=1` and `max_overflow=0` avoid a large per-container connection pool.
- Main customer product list/detail paths use `selectinload` and batch review/offer aggregation.
- Admin taxonomy lists compute product counts in grouped/window queries rather than one count per taxonomy row.
- Customer order items, products, brands, categories, variants, images, addresses, and pickup stores are eagerly loaded on the normal path.
- `app/core/order_lens_fit.py` batch-loads web-order lens fits for a page with one order query plus `selectinload`, avoiding one query per store order.
- Warehouse pending-delivery rows eager-load order items/products before serialization.
- Store POS validates variants and inventory with bulk `IN` queries rather than per-line lookups.
- `collection_ids_for` batches taxonomy resolution (use as the template for brand/category).
- Admin dashboards/reports/home use single CTE/SQL payloads rather than per-widget queries.
- The Telegram notification SQS client is cached per warm Lambda container.

## Recommended implementation order

1. Rotate and remove committed secrets / dump / deploy keys; add `.samignore` (F1).
2. Make Razorpay `verify_payment` idempotent with a unique payment id constraint (F1b).
3. Move Shiprocket booking/pickup to an idempotent outbox + SQS worker (F3, F10).
4. Set the HTTP Lambda timeout and reserved concurrency to explicit safe values (F2, F9).
5. Replace warehouse dispatch, receiving, and transfer query loops with bulk locked reads/upserts (F4–F6).
6. Batch checkout variant resolution, bulk-import taxonomy lookups, and paginated window counts (F7, F14, F15).
7. Remove legacy pickup fallback after backfill; tighten offer SQL and clinical store resolution (F8, F16, F17).
8. Slim the Lambda package and add access logs/tracing/alarms (F12, F13).

## Verification plan for the proposed fixes

- Add SQL query-count tests for 1, 10, and 50 line-item requests; counts should remain constant or grow by a small fixed number, not linearly.
- Run concurrent inventory tests proving stock cannot become negative and partial transfers/receipts roll back.
- Retry `verify_payment` with the same `razorpay_payment_id` and assert exactly one order row.
- Inject Shiprocket latency/failures and verify checkout still returns quickly with one order and one durable fulfillment job.
- Load-test Lambda at the reserved concurrency and verify PgBouncer/database connections stay below the agreed budget.
- Check CloudWatch `Init Duration`, package size (~131 MB baseline), p95 duration, and max memory before/after dependency cleanup.
- Verify secret scanning passes both the current tree and Git history after credential rotation/history-remediation decisions.
- Confirm the Lambda zip no longer contains `backups/`, `deploy.sh`, or dump files.
