from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.api import CurrentUserRead

router = APIRouter(prefix="/auth", tags=["identity"])


@router.get("/me", response_model=CurrentUserRead)
def current_identity(user: CurrentUser = Depends(get_current_user)) -> CurrentUserRead:
    return CurrentUserRead(id=user.id, email=user.email, role=user.role)
