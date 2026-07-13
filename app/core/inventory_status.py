"""SQL CASE expressions for inventory stock-health status."""

from sqlalchemy import case, literal


def warehouse_stock_status(on_hand, reorder_point):
    """Critical / Low / Overstock / Healthy from on_hand vs reorder_point."""
    return case(
        (on_hand == 0, literal("Critical")),
        (on_hand < reorder_point * 0.5, literal("Critical")),
        (on_hand < reorder_point, literal("Low")),
        (on_hand > reorder_point * 6, literal("Overstock")),
        else_=literal("Healthy"),
    )


def store_stock_status(total_on_hand, reorder_point):
    """Critical / Low / Overstock / Healthy from floor+backroom vs reorder."""
    return case(
        (total_on_hand == 0, literal("Critical")),
        (total_on_hand < reorder_point * 0.5, literal("Critical")),
        (total_on_hand < reorder_point, literal("Low")),
        (total_on_hand > reorder_point * 4, literal("Overstock")),
        else_=literal("Healthy"),
    )
