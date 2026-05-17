from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import (
    UserCreate,
    UserUpdate,
    PasswordChange,
    AdminPasswordReset,
    UserResponse,
    UserListResponse,
)
from app.database import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


class TokenResponse(UserResponse):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(UserResponse):
    refresh_token: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
):
    try:
        payload = service.decode_token(token)
        username: str = payload.get("sub")
        if not username or payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await service.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account deactivated")
    return user


async def get_current_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
):
    user = await service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = service.create_access_token({"sub": user.username})
    refresh_token = service.create_refresh_token({"sub": user.username})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_session)):
    try:
        payload = service.decode_token(body.refresh_token)
        username: str = payload.get("sub")
        if not username or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await service.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = service.create_access_token({"sub": user.username})
    refresh_token = service.create_refresh_token({"sub": user.username})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# --- Self-service endpoints ---


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    try:
        user = await service.update_username(db, current_user.id, body.username)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("/me/change-password", status_code=204)
async def change_my_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    success = await service.change_password(
        db, current_user.id, body.current_password, body.new_password
    )
    if not success:
        raise HTTPException(status_code=400, detail="Current password is incorrect")


# --- Admin user management router ---

users_router = APIRouter(prefix="/api/users", tags=["users"])


@users_router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_admin),
):
    try:
        user = await service.create_user(db, body.username, body.password, body.is_admin)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return UserResponse.model_validate(user)


@users_router.get("", response_model=UserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_admin),
):
    users = await service.list_users(db)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@users_router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_admin),
):
    try:
        user = await service.update_username(db, user_id, body.username)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return UserResponse.model_validate(user)


@users_router.post("/{user_id}/set-password", status_code=204)
async def set_user_password(
    user_id: int,
    body: AdminPasswordReset,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_admin),
):
    success = await service.admin_set_password(db, user_id, body.new_password)
    if not success:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")


@users_router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin=Depends(get_current_admin),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    success = await service.deactivate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
