"""Razorpay client (single instance, reused across warm Lambda invocations)."""

import razorpay
from razorpay import errors  # re-exported for routers that need error classes

from app.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

__all__ = ["client", "errors"]
