"""Move inline product data URLs to the configured public S3 bucket.

Safe to rerun: only values that still start with ``data:image/`` are migrated.

    python -m scripts.migrate_inline_product_images
"""

from __future__ import annotations

import base64
import binascii
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import S3_PUBLIC_BUCKET, S3_PUBLIC_REGION
from app.core.s3_images import ALLOWED_CONTENT_TYPES, object_key, public_url_for
from app.database import SessionLocal
from app.schemas import ProductImage, ProductVariant

MAX_DECODED_BYTES = 10 * 1024 * 1024


def _decode_data_url(value: str) -> tuple[str, bytes]:
    header, separator, encoded = value.partition(",")
    if not separator or not header.lower().startswith("data:image/"):
        raise ValueError("Not an inline image data URL.")
    media_part = header[5:].split(";")
    content_type = media_part[0].lower()
    if "base64" not in {part.lower() for part in media_part[1:]}:
        raise ValueError("Inline image is not base64 encoded.")
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Unsupported inline image type: {content_type}")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Inline image has invalid base64 data.") from error
    if not data:
        raise ValueError("Inline image is empty.")
    if len(data) > MAX_DECODED_BYTES:
        raise ValueError("Inline image exceeds the 10 MB migration limit.")
    return content_type, data


def _upload(product_id: int, value: str) -> str:
    content_type, data = _decode_data_url(value)
    key = object_key(product_id, content_type)
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            "-",
            f"s3://{S3_PUBLIC_BUCKET}/{key}",
            "--content-type",
            content_type,
            "--cache-control",
            "public, max-age=31536000, immutable",
            "--region",
            S3_PUBLIC_REGION,
            "--only-show-errors",
        ],
        input=data,
        check=True,
    )
    return public_url_for(key)


def migrate() -> None:
    if not S3_PUBLIC_BUCKET:
        raise RuntimeError("S3_PUBLIC_BUCKET is not configured.")

    db = SessionLocal()
    uploaded = 0
    try:
        gallery_images = list(
            db.scalars(
                select(ProductImage)
                .where(ProductImage.url.ilike("data:image/%"))
                .order_by(ProductImage.id)
            ).all()
        )
        variants = list(db.scalars(select(ProductVariant).order_by(ProductVariant.id)).all())
        variant_images = sum(
            1
            for variant in variants
            for url in (variant.images or [])
            if isinstance(url, str) and url.lower().startswith("data:image/")
        )
        print(
            f"Found {len(gallery_images)} inline gallery images and "
            f"{variant_images} inline variant images."
        )

        for image in gallery_images:
            image.url = _upload(image.product_id, image.url)
            uploaded += 1
            print(f"Uploaded gallery image {uploaded}/{len(gallery_images) + variant_images}")

        for variant in variants:
            changed = False
            urls: list[str] = []
            for url in variant.images or []:
                if isinstance(url, str) and url.lower().startswith("data:image/"):
                    urls.append(_upload(variant.product_id, url))
                    uploaded += 1
                    changed = True
                    print(
                        f"Uploaded variant image {uploaded}/"
                        f"{len(gallery_images) + variant_images}"
                    )
                else:
                    urls.append(url)
            if changed:
                variant.images = urls

        db.commit()
        print(f"Done. Migrated {uploaded} inline images to S3.")
    except (subprocess.CalledProcessError, ValueError):
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
