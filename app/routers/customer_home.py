"""Cached, single-query homepage payload for the customer storefront."""

from json import loads
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dto.customer_home_dto import CustomerHomeResponse

router = APIRouter(prefix="/customer/home", tags=["customer-home"])

_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=86400"

# The database is remote, so every SQL statement has a material latency cost.
# This query returns the complete homepage in one round-trip and deliberately
# projects only fields used by homepage cards.
_HOME_SQL = text(
    """
    WITH product_pool AS MATERIALIZED (
        SELECT
            p.id AS db_id,
            p.slug AS id,
            p.name,
            coalesce(nullif(p.selling_price, 0), p.price, 0) AS base_price,
            p.brand_id,
            p.category_id,
            p.gender,
            p.is_bestseller,
            p.is_new
        FROM products p
        WHERE p.status = 'active'
        ORDER BY p.id ASC
        LIMIT 24
    ),
    cards AS MATERIALIZED (
        SELECT
            p.db_id,
            p.id,
            p.name,
            round(
                greatest(
                    0,
                    p.base_price - coalesce(
                        least(
                            p.base_price,
                            CASE
                                WHEN winner.discount_type = 'PERCENTAGE' THEN
                                    least(
                                        p.base_price * winner.discount_value / 100,
                                        coalesce(winner.maximum_discount, p.base_price)
                                    )
                                ELSE winner.discount_value
                            END
                        ),
                        0
                    )
                ),
                2
            )::double precision AS price,
            coalesce(image.url, '') AS image,
            coalesce(inventory.stock, 0)::integer AS stock,
            coalesce(reviews.rating, 0)::double precision AS rating,
            coalesce(swatches.colors, '[]'::json) AS color_swatches,
            p.is_bestseller,
            p.is_new
        FROM product_pool p
        LEFT JOIN LATERAL (
            SELECT pi.url
            FROM product_images pi
            WHERE pi.product_id = p.db_id
            ORDER BY pi.sort_order ASC, pi.id ASC
            LIMIT 1
        ) image ON TRUE
        LEFT JOIN LATERAL (
            SELECT coalesce(sum(pv.stock), 0) AS stock
            FROM product_variants pv
            WHERE
                pv.product_id = p.db_id
                AND coalesce(pv.color, '') != '__deleted__'
                AND coalesce(pv.size, '') != '__deleted__'
        ) inventory ON TRUE
        LEFT JOIN LATERAL (
            SELECT round(avg(pr.rating)::numeric, 1) AS rating
            FROM product_reviews pr
            WHERE pr.product_id = p.db_id AND pr.status = 'approved'
        ) reviews ON TRUE
        LEFT JOIN LATERAL (
            SELECT json_agg(s.color_hex ORDER BY s.first_id) AS colors
            FROM (
                SELECT pv.color_hex, min(pv.id) AS first_id
                FROM product_variants pv
                WHERE
                    pv.product_id = p.db_id
                    AND pv.color_hex IS NOT NULL
                    AND pv.color_hex != ''
                    AND coalesce(pv.color, '') != '__deleted__'
                    AND coalesce(pv.size, '') != '__deleted__'
                GROUP BY pv.color_hex
                ORDER BY min(pv.id)
                LIMIT 3
            ) s
        ) swatches ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                o.discount_type,
                o.discount_value,
                o.maximum_discount
            FROM offers o
            WHERE
                o.status NOT IN ('inactive', 'deleted')
                AND o.start_date <= now()
                AND o.end_date >= now()
                AND (
                    (o.apply_on = 'PRODUCT' AND o.product_id = p.db_id)
                    OR (o.apply_on = 'BRAND' AND o.brand_id = p.brand_id)
                    OR (o.apply_on = 'CATEGORY' AND o.category_id = p.category_id)
                    OR (
                        o.apply_on = 'GENDER'
                        AND CASE upper(trim(coalesce(o.gender, '')))
                            WHEN 'MEN' THEN 'MALE'
                            WHEN 'MAN' THEN 'MALE'
                            WHEN 'WOMEN' THEN 'FEMALE'
                            WHEN 'WOMAN' THEN 'FEMALE'
                            ELSE upper(trim(coalesce(o.gender, '')))
                        END = CASE upper(trim(coalesce(p.gender, '')))
                            WHEN 'MEN' THEN 'MALE'
                            WHEN 'MAN' THEN 'MALE'
                            WHEN 'WOMEN' THEN 'FEMALE'
                            WHEN 'WOMAN' THEN 'FEMALE'
                            ELSE upper(trim(coalesce(p.gender, '')))
                        END
                    )
                )
            ORDER BY o.priority DESC, o.id DESC
            LIMIT 1
        ) winner ON TRUE
    ),
    category_cards AS MATERIALIZED (
        SELECT
            cat.id,
            cat.slug,
            cat.name,
            count(p.id) FILTER (WHERE p.status = 'active')::integer AS count,
            coalesce((
                SELECT pi.url
                FROM products p2
                JOIN product_images pi ON pi.product_id = p2.id
                WHERE p2.category_id = cat.id AND p2.status = 'active'
                ORDER BY p2.id ASC, pi.sort_order ASC, pi.id ASC
                LIMIT 1
            ), '') AS image
        FROM categories cat
        LEFT JOIN products p ON p.category_id = cat.id
        WHERE cat.status = 'active'
        GROUP BY cat.id, cat.slug, cat.name
    )
    SELECT json_build_object(
        'banners', (
            SELECT coalesce(json_agg(b ORDER BY b.sort_order, b.id), '[]'::json)
            FROM (
                SELECT
                    id,
                    eyebrow,
                    title,
                    subtitle,
                    brand_line,
                    image_url,
                    image_alt,
                    cta_label,
                    category,
                    sort_order,
                    is_active
                FROM home_banners
                WHERE is_active IS TRUE
            ) b
        ),
        'mobile_banners', (
            SELECT coalesce(json_agg(m ORDER BY m.sort_order, m.id), '[]'::json)
            FROM (
                SELECT
                    id,
                    title,
                    subtitle,
                    media_url,
                    media_type,
                    media_alt,
                    cta_label,
                    category,
                    sort_order,
                    is_active
                FROM mobile_banners
                WHERE is_active IS TRUE
            ) m
        ),
        'categories', (
            SELECT coalesce(
                json_agg(
                    json_build_object(
                        'id', id,
                        'slug', slug,
                        'name', name,
                        'image', image,
                        'count', count
                    )
                    ORDER BY name
                ),
                '[]'::json
            )
            FROM category_cards
        ),
        'products', (
            SELECT coalesce(
                json_agg(
                    json_build_object(
                        'id', id,
                        'name', name,
                        'price', price,
                        'image', image,
                        'stock', stock,
                        'rating', rating,
                        'colorSwatches', color_swatches
                    )
                    ORDER BY db_id
                ),
                '[]'::json
            )
            FROM cards
        ),
        'featured', (
            SELECT coalesce(json_agg(id ORDER BY db_id), '[]'::json)
            FROM (
                SELECT id, db_id FROM cards ORDER BY db_id LIMIT 8
            ) featured_cards
        ),
        'bestsellers', (
            SELECT coalesce(json_agg(id ORDER BY db_id), '[]'::json)
            FROM (
                SELECT id, db_id
                FROM cards
                WHERE
                    is_bestseller
                    OR (SELECT count(*) FROM cards WHERE is_bestseller) < 8
                ORDER BY db_id
                LIMIT 8
            ) bestseller_cards
        ),
        'newArrivals', (
            SELECT coalesce(json_agg(id ORDER BY db_id), '[]'::json)
            FROM (
                SELECT id, db_id
                FROM cards
                WHERE is_new OR (SELECT count(*) FROM cards WHERE is_new) < 8
                ORDER BY db_id
                LIMIT 8
            ) new_cards
        )
    )
    """
)


def _payload(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        return loads(value)
    return dict(value)


@router.get("", response_model=CustomerHomeResponse)
def customer_home(
    response: Response,
    db: Session = Depends(get_db),
) -> CustomerHomeResponse:
    response.headers["Cache-Control"] = _CACHE_CONTROL
    response.headers["CDN-Cache-Control"] = _CACHE_CONTROL
    return CustomerHomeResponse.model_validate(_payload(db.execute(_HOME_SQL).scalar()))
