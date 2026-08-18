"""Resolve the single highest-priority automatic offer for storefront products."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas import Offer, Product


@dataclass(frozen=True)
class OfferPrice:
    offer_id: int
    offer_name: str
    label: str
    discount: Decimal
    final_price: Decimal


def _gender_key(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    return {
        "MEN": "MALE",
        "MAN": "MALE",
        "WOMEN": "FEMALE",
        "WOMAN": "FEMALE",
    }.get(normalized, normalized)


def _applies(offer: Offer, product: Product) -> bool:
    if offer.apply_on == "PRODUCT":
        return offer.product_id == product.id
    if offer.apply_on == "BRAND":
        return offer.brand_id is not None and offer.brand_id == product.brand_id
    if offer.apply_on == "CATEGORY":
        return offer.category_id is not None and offer.category_id == product.category_id
    if offer.apply_on == "GENDER":
        return _gender_key(offer.gender) == _gender_key(product.gender)
    return False


def price_for_offer(
    offer: Offer, product: Product, base_price: Decimal | None = None
) -> OfferPrice:
    base_price = base_price or Decimal(product.selling_price or product.price)
    if offer.discount_type == "PERCENTAGE":
        discount = base_price * Decimal(offer.discount_value) / Decimal("100")
        if offer.maximum_discount is not None:
            discount = min(discount, Decimal(offer.maximum_discount))
        label = f"{Decimal(offer.discount_value):g}% OFF"
    else:
        discount = Decimal(offer.discount_value)
        label = f"₹{Decimal(offer.discount_value):g} OFF"

    discount = min(base_price, discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return OfferPrice(
        offer_id=offer.id,
        offer_name=offer.name,
        label=label,
        discount=discount,
        final_price=(base_price - discount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    )


def winning_offers_for(db: Session, products: list[Product]) -> dict[int, Offer]:
    """Return the highest-priority active offer per product; offers never stack."""
    if not products:
        return {}

    offers = db.scalars(
        select(Offer)
        .where(
            Offer.status.notin_(("inactive", "deleted")),
            Offer.start_date <= func.now(),
            Offer.end_date >= func.now(),
        )
        .order_by(Offer.priority.desc(), Offer.id.desc())
    ).all()

    resolved: dict[int, Offer] = {}
    for product in products:
        winner = next((offer for offer in offers if _applies(offer, product)), None)
        if winner is not None:
            resolved[product.id] = winner
    return resolved


def offer_prices_for(db: Session, products: list[Product]) -> dict[int, OfferPrice]:
    winners = winning_offers_for(db, products)
    return {
        product.id: price_for_offer(winners[product.id], product)
        for product in products
        if product.id in winners
    }
