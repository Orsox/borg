from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def create_user(
    db: AsyncSession, username: str, password: str, is_admin: bool = False
) -> User:
    existing = await get_user_by_username(db, username)
    if existing:
        raise ValueError(f"Username '{username}' already taken")
    user = User(
        username=username,
        hashed_password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_username(
    db: AsyncSession, user_id: int, new_username: str
):
    conflict = await get_user_by_username(db, new_username)
    if conflict and conflict.id != user_id:
        raise ValueError(f"Username '{new_username}' already taken")
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    user.username = new_username
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(
    db: AsyncSession, user_id: int, current_password: str, new_password: str
) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user or not verify_password(current_password, user.hashed_password):
        return False
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return True


async def admin_set_password(
    db: AsyncSession, user_id: int, new_password: str
) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return True


async def deactivate_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    user.is_active = False
    await db.commit()
    return True


async def seed_default_user(db: AsyncSession) -> None:
    existing = await get_user_by_username(db, "borg")
    if existing:
        # Upgrade path: ensure borg is admin
        if not existing.is_admin:
            existing.is_admin = True
            await db.commit()
        return
    user = User(
        username="borg",
        hashed_password=hash_password(settings.initial_password),
        is_admin=True,
    )
    db.add(user)
    await db.commit()
