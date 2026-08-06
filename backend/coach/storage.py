"""Proof screenshots — one thin seam over S3-compatible object storage.

Cloudflare R2 today. Nothing vendor-specific may leak out of this module: the
rest of the app deals in opaque keys, so moving to another S3-compatible
provider is an endpoint change in settings, not a code change.

Every function here is optional by construction. `is_configured()` is false
until the bucket credentials exist, and callers must treat storage being
absent as an ordinary state, not an error — the daily loop predates
screenshots and has to keep working without them.
"""

import uuid
from functools import lru_cache

import boto3
from botocore.config import Config
from django.conf import settings
from loguru import logger

# How long a link to a builder's own proof stays valid. Short: the dashboard
# mints a fresh one every time it loads, and these images are private work
# records that should not survive as shareable URLs in someone's history.
VIEW_URL_TTL = 300


def is_configured() -> bool:
    return bool(
        settings.R2_ENDPOINT
        and settings.R2_BUCKET
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
    )


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        # R2 ignores the region but botocore insists on one being present.
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
    )


def proof_key(goal_id: int, checkin_id: int, content_type: str) -> str:
    """Namespaced by goal so a bucket listing can't be read as one flat feed
    of everyone's evidence, and suffixed randomly so a re-upload on the same
    check-in never silently overwrites the image already on the record."""
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[content_type]
    return f"proofs/{goal_id}/{checkin_id}-{uuid.uuid4().hex[:12]}.{ext}"


def put_image(key: str, data: bytes, content_type: str) -> bool:
    """Store one proof image. Returns whether it landed.

    Never raises: a failed upload must not cost the builder their proof. The
    text of the check-in is the proof of record; the screenshot is corroboration.
    """
    try:
        _client().put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return True
    except Exception as e:
        logger.error(f"Proof image upload failed for {key}: {e}")
        return False


def view_url(key: str) -> str:
    """A short-lived signed URL for the builder to see their own proof.

    Signed rather than public: the bucket stays private, so an image is only
    reachable by someone the server just handed a link to. Returns "" on
    failure so a serializer can omit the image rather than 500 the dashboard.
    """
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET, "Key": key},
            ExpiresIn=VIEW_URL_TTL,
        )
    except Exception as e:
        logger.error(f"Presigning failed for {key}: {e}")
        return ""
