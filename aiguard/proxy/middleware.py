"""
Auth middleware: resolves the incoming AIGuard key to an Org + User identity.

Key format: "aip_<org_slug>_<32 random hex chars>"
The first 8 chars after "aip_<slug>_" are the key_prefix used for O(1) DB lookup.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import HTTPException, Request, status
from sqlalchemy import select

from aiguard.config import settings
from aiguard.db.engine import async_session_factory
from aiguard.db.models.api_key import ApiKey
from aiguard.db.models.org import Org
from aiguard.db.models.user import User

logger = logging.getLogger(__name__)


def _key_bytes(raw_key: str) -> bytes:
    """SHA-256 the key first — bcrypt has a 72-byte input limit."""
    return hashlib.sha256(raw_key.encode()).digest()


def hash_key(raw_key: str) -> str:
    return bcrypt.hashpw(_key_bytes(raw_key), bcrypt.gensalt()).decode()


def verify_key(raw_key: str, hashed: str) -> bool:
    return bcrypt.checkpw(_key_bytes(raw_key), hashed.encode())


def generate_api_key(org_slug: str) -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_key, key_prefix, key_hash).
    The full_key is shown to the user once and never stored.
    """
    import secrets
    random_part = secrets.token_hex(20)  # 40 hex chars
    full_key = f"aip_{org_slug}_{random_part}"
    key_prefix = full_key[:16]  # first 16 chars for lookup
    key_hash = hash_key(full_key)
    return full_key, key_prefix, key_hash


class ProxyIdentity:
    """Resolved identity attached to request.state.identity"""

    def __init__(
        self,
        api_key: ApiKey,
        org: Org,
        user: User | None,
        upstream_key: str | None,
    ) -> None:
        self.api_key = api_key
        self.org = org
        self.user = user
        self.upstream_key = upstream_key  # decrypted upstream API key (if key-vault mode)

    @property
    def org_id(self) -> str:
        return str(self.org.id)

    @property
    def user_id(self) -> str | None:
        return str(self.user.id) if self.user else None

    def merged_policy(self) -> dict:
        """Merge org policy with user overrides. User wins."""
        policy = dict(self.org.policy)
        if self.user:
            policy.update(self.user.policy_overrides)
        return policy


async def resolve_identity(request: Request) -> ProxyIdentity:
    """
    Extract and validate the AIGuard key from the Authorization header.
    Returns a ProxyIdentity or raises HTTPException 401/403.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer <shield-key>",
        )

    raw_key = auth.removeprefix("Bearer ").strip()

    if not raw_key.startswith("aip_"):
        # Passthrough mode: treat as a real upstream key, no identity resolution
        if settings.passthrough_mode:
            return _passthrough_identity(raw_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid AIGuard key format. Expected: aip_<org>_<key>",
        )

    key_prefix = raw_key[:16]

    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.key_prefix == key_prefix,
                ApiKey.is_active == True,  # noqa: E712
            )
        )
        api_keys = result.scalars().all()

    # Find the matching key by verifying the bcrypt hash
    matched: ApiKey | None = None
    for candidate in api_keys:
        if verify_key(raw_key, candidate.key_hash):
            matched = candidate
            break

    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    # Check expiry
    if matched.expires_at and matched.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    # Load org and user
    async with async_session_factory() as session:
        org = await session.get(Org, matched.org_id)
        user = await session.get(User, matched.user_id) if matched.user_id else None

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization not found",
        )

    if user and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Resolve upstream key
    upstream_key: str | None = None
    if matched.upstream_key_encrypted:
        from aiguard.crypto import decrypt
        try:
            upstream_key = decrypt(matched.upstream_key_encrypted)
        except Exception:
            logger.error("Failed to decrypt upstream key for api_key_id=%s", matched.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to resolve upstream API key",
            )

    # Update last_used_at (fire-and-forget)
    import asyncio
    asyncio.create_task(_update_last_used(matched.id))

    return ProxyIdentity(api_key=matched, org=org, user=user, upstream_key=upstream_key)


# Stable UUIDs for passthrough mode — ensures FK constraints are satisfied.
_PASSTHROUGH_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
_PASSTHROUGH_KEY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _passthrough_identity(raw_key: str) -> ProxyIdentity:
    """
    In passthrough mode, we create a minimal identity that just carries
    the upstream key. No user/org lookup.
    Uses stable UUIDs so audit log FK constraints are satisfied.
    """

    class _FakeOrg:
        id = _PASSTHROUGH_ORG_ID
        policy = {}
        slug = "passthrough"

    class _FakeKey:
        id = _PASSTHROUGH_KEY_ID
        org_id = _PASSTHROUGH_ORG_ID
        user_id = None
        upstream_key_encrypted = None

    fake_identity = ProxyIdentity(
        api_key=_FakeKey(),  # type: ignore[arg-type]
        org=_FakeOrg(),  # type: ignore[arg-type]
        user=None,
        upstream_key=raw_key,  # use the raw key as-is upstream
    )
    return fake_identity


async def _update_last_used(api_key_id) -> None:
    try:
        async with async_session_factory() as session:
            key = await session.get(ApiKey, api_key_id)
            if key:
                key.last_used_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as exc:
        logger.debug("Failed to update last_used_at: %s", exc)
