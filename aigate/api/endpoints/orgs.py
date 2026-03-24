from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from aigate.db.engine import async_session_factory
from aigate.db.models.org import Org

router = APIRouter(prefix="/orgs", tags=["orgs"])


class OrgCreate(BaseModel):
    name: str
    slug: str | None = None
    policy: dict = {}


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    policy: dict


def _make_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]


@router.post("", response_model=OrgResponse, status_code=201)
async def create_org(data: OrgCreate):
    slug = data.slug or _make_slug(data.name)
    async with async_session_factory() as session:
        existing = await session.execute(select(Org).where(Org.slug == slug))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Org slug '{slug}' already exists")
        org = Org(name=data.name, slug=slug, policy=data.policy)
        session.add(org)
        await session.commit()
        await session.refresh(org)
    return OrgResponse(id=str(org.id), name=org.name, slug=org.slug, policy=org.policy)


@router.get("", response_model=list[OrgResponse])
async def list_orgs():
    async with async_session_factory() as session:
        result = await session.execute(select(Org))
        orgs = result.scalars().all()
    return [OrgResponse(id=str(o.id), name=o.name, slug=o.slug, policy=o.policy) for o in orgs]


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(org_id: str):
    async with async_session_factory() as session:
        org = await session.get(Org, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    return OrgResponse(id=str(org.id), name=org.name, slug=org.slug, policy=org.policy)


@router.patch("/{org_id}/policy", response_model=OrgResponse)
async def update_policy(org_id: str, policy: dict):
    async with async_session_factory() as session:
        org = await session.get(Org, uuid.UUID(org_id))
        if not org:
            raise HTTPException(status_code=404, detail="Org not found")
        org.policy = policy
        await session.commit()
        await session.refresh(org)
    return OrgResponse(id=str(org.id), name=org.name, slug=org.slug, policy=org.policy)


@router.delete("/{org_id}", status_code=204)
async def delete_org(org_id: str):
    async with async_session_factory() as session:
        org = await session.get(Org, uuid.UUID(org_id))
        if not org:
            raise HTTPException(status_code=404, detail="Org not found")
        await session.delete(org)
        await session.commit()
