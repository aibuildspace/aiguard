from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from aigate.db.engine import async_session_factory
from aigate.db.models.api_key import ApiKey
from aigate.proxy.middleware import generate_api_key

router = APIRouter(prefix="/keys", tags=["api-keys"])


class KeyCreate(BaseModel):
    org_id: str
    user_id: str | None = None
    label: str = ""
    provider: str = "any"
    upstream_key: str | None = None  # store encrypted in key-vault mode


class KeyCreateResponse(BaseModel):
    id: str
    key: str  # Full key shown ONCE
    key_prefix: str
    label: str
    provider: str


class KeyResponse(BaseModel):
    id: str
    org_id: str
    user_id: str | None
    key_prefix: str
    label: str
    provider: str
    is_active: bool
    last_used_at: str | None
    has_upstream_key: bool = False


class KeyUpdate(BaseModel):
    upstream_key: str | None = None
    label: str | None = None


@router.post("", response_model=KeyCreateResponse, status_code=201)
async def create_key(data: KeyCreate):
    from aigate.db.models.org import Org

    async with async_session_factory() as session:
        org = await session.get(Org, uuid.UUID(data.org_id))
        if not org:
            raise HTTPException(status_code=404, detail="Org not found")

        full_key, key_prefix, key_hash = generate_api_key(org.slug)

        upstream_encrypted = None
        if data.upstream_key:
            from aigate.crypto import encrypt
            upstream_encrypted = encrypt(data.upstream_key)

        api_key = ApiKey(
            org_id=uuid.UUID(data.org_id),
            user_id=uuid.UUID(data.user_id) if data.user_id else None,
            key_prefix=key_prefix,
            key_hash=key_hash,
            label=data.label,
            provider=data.provider,
            upstream_key_encrypted=upstream_encrypted,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

    return KeyCreateResponse(
        id=str(api_key.id),
        key=full_key,
        key_prefix=key_prefix,
        label=data.label,
        provider=data.provider,
    )


@router.get("", response_model=list[KeyResponse])
async def list_keys(org_id: str | None = None, user_id: str | None = None):
    async with async_session_factory() as session:
        q = select(ApiKey)
        if org_id:
            q = q.where(ApiKey.org_id == uuid.UUID(org_id))
        if user_id:
            q = q.where(ApiKey.user_id == uuid.UUID(user_id))
        result = await session.execute(q)
        keys = result.scalars().all()
    return [_to_response(k) for k in keys]


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: str):
    async with async_session_factory() as session:
        key = await session.get(ApiKey, uuid.UUID(key_id))
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        key.is_active = False
        await session.commit()


@router.patch("/{key_id}")
async def update_key(key_id: str, data: KeyUpdate):
    """Update an API key's upstream key or label."""
    async with async_session_factory() as session:
        key = await session.get(ApiKey, uuid.UUID(key_id))
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")

        if data.label is not None:
            key.label = data.label

        if data.upstream_key is not None:
            if data.upstream_key == "":
                key.upstream_key_encrypted = None
            else:
                from aigate.crypto import encrypt
                key.upstream_key_encrypted = encrypt(data.upstream_key)

        await session.commit()
    return {"ok": True}


@router.delete("", status_code=200)
async def delete_all_keys():
    """Hard-delete every API key."""
    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey))
        keys = result.scalars().all()
        count = len(keys)
        for k in keys:
            await session.delete(k)
        await session.commit()
    return {"deleted": count}


def _to_response(key: ApiKey) -> KeyResponse:
    return KeyResponse(
        id=str(key.id),
        org_id=str(key.org_id),
        user_id=str(key.user_id) if key.user_id else None,
        key_prefix=key.key_prefix,
        label=key.label,
        provider=key.provider,
        is_active=key.is_active,
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
        has_upstream_key=bool(key.upstream_key_encrypted),
    )
