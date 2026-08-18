"""Presigned uploads to the public catalog bucket.

Objects are keyed per product (or a pending namespace before creation):
  catalog/products/{product_id}/{uuid}.{ext}
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.core.config import (
    S3_PRESIGN_EXPIRES_SECONDS,
    S3_PUBLIC_BASE_URL,
    S3_PUBLIC_BUCKET,
    S3_PUBLIC_REGION,
)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

EXT_TO_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

MAX_FILES_PER_PRESIGN = 25


def _s3():
    # when_required avoids signing checksum headers that browsers cannot send
    # on a presigned PUT, which otherwise fails with SignatureDoesNotMatch.
    # Force the regional endpoint. Botocore can otherwise use the legacy global
    # s3.amazonaws.com endpoint while signing for ap-south-2; S3 rejects that
    # combination with IllegalLocationConstraintException.
    return boto3.client(
        "s3",
        region_name=S3_PUBLIC_REGION,
        endpoint_url=f"https://s3.{S3_PUBLIC_REGION}.amazonaws.com",
        config=BotoConfig(
            signature_version="s3v4",
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={"addressing_style": "virtual"},
        ),
    )


def resolve_content_type(filename: str, content_type: str) -> str:
    raw = (content_type or "").split(";")[0].strip().lower()
    if raw in ALLOWED_CONTENT_TYPES:
        return "image/jpeg" if raw == "image/jpg" else raw
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapped = EXT_TO_CONTENT_TYPE.get(ext)
    if mapped:
        return mapped
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported image type for {filename or 'file'}. Use JPEG, PNG, WebP, or GIF.",
    )


def object_key(product_id: int | str, content_type: str) -> str:
    ext = ALLOWED_CONTENT_TYPES[content_type]
    return f"catalog/products/{product_id}/{uuid.uuid4().hex}.{ext}"


def banner_object_key(content_type: str) -> str:
    ext = ALLOWED_CONTENT_TYPES[content_type]
    return f"homepage/banners/{uuid.uuid4().hex}.{ext}"


def public_url_for(key: str) -> str:
    return f"{S3_PUBLIC_BASE_URL.rstrip('/')}/{key}"


def _presign_puts(
    files: list[tuple[str, str]],
    key_for_content_type: Callable[[str], str],
) -> list[dict[str, str]]:
    if not S3_PUBLIC_BUCKET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image storage is not configured (S3_PUBLIC_BUCKET).",
        )
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add at least one image file.",
        )
    if len(files) > MAX_FILES_PER_PRESIGN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {MAX_FILES_PER_PRESIGN} images per upload batch.",
        )

    client = _s3()
    uploads: list[dict[str, str]] = []
    try:
        for filename, content_type in files:
            resolved = resolve_content_type(filename, content_type)
            key = key_for_content_type(resolved)
            put_url = client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": S3_PUBLIC_BUCKET,
                    "Key": key,
                    "ContentType": resolved,
                },
                ExpiresIn=S3_PRESIGN_EXPIRES_SECONDS,
            )
            uploads.append(
                {
                    "key": key,
                    "put_url": put_url,
                    "public_url": public_url_for(key),
                    "content_type": resolved,
                }
            )
    except (BotoCoreError, ClientError) as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create an upload URL for S3. Check Lambda access to renown-public.",
        ) from err
    return uploads


def presign_puts(
    product_id: int | str, files: list[tuple[str, str]]
) -> list[dict[str, str]]:
    return _presign_puts(files, lambda content_type: object_key(product_id, content_type))


def presign_banner_puts(files: list[tuple[str, str]]) -> list[dict[str, str]]:
    return _presign_puts(files, banner_object_key)


def delete_banner_object(key: str) -> bool:
    """Best-effort cleanup after banner metadata is replaced or deleted."""
    if not S3_PUBLIC_BUCKET or not key.startswith("homepage/banners/"):
        return False
    try:
        _s3().delete_object(Bucket=S3_PUBLIC_BUCKET, Key=key)
        return True
    except (BotoCoreError, ClientError):
        return False
