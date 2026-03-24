from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from aigate.db.engine import async_session_factory
from aigate.db.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    org_id: str
    email: str
    name: str
    role: str = "member"


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    name: str
    role: str
    is_active: bool


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(data: UserCreate):
    async with async_session_factory() as session:
        existing = await session.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(
            org_id=uuid.UUID(data.org_id),
            email=data.email,
            name=data.name,
            role=data.role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return _to_response(user)


@router.get("", response_model=list[UserResponse])
async def list_users(org_id: str | None = None):
    async with async_session_factory() as session:
        q = select(User)
        if org_id:
            q = q.where(User.org_id == uuid.UUID(org_id))
        result = await session.execute(q)
        users = result.scalars().all()
    return [_to_response(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    async with async_session_factory() as session:
        user = await session.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_response(user)


@router.patch("/{user_id}/disable", response_model=UserResponse)
async def disable_user(user_id: str):
    async with async_session_factory() as session:
        user = await session.get(User, uuid.UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False
        await session.commit()
        await session.refresh(user)
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, data: UserUpdate):
    async with async_session_factory() as session:
        user = await session.get(User, uuid.UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if data.name is not None:
            user.name = data.name
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        await session.commit()
        await session.refresh(user)
    return _to_response(user)


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        org_id=str(user.org_id),
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
    )
