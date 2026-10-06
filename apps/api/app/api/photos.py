from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.projects import get_project_for_role_or_404
from app.core.security import CurrentUser, get_current_human_user
from app.db.session import get_db
from app.services import google_photos as photos
from app.services.audit import audit
from app.services.rate_limits import enforce_project_rate_limit

router = APIRouter(tags=["google-photos"])


def owner(project_id: str, request: Request, db: Session = Depends(get_db),
          user: CurrentUser = Depends(get_current_human_user)):
    get_project_for_role_or_404(db, project_id, user, "owner", request, "photos.access")
    return user


@router.get("/projects/{project_id}/photos")
def photos_status(project_id: str, db: Session = Depends(get_db), user=Depends(owner)):
    try:
        return photos.status(db, project_id)
    except photos.PhotosError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/projects/{project_id}/photos/connect")
def photos_connect(project_id: str, request: Request, db: Session = Depends(get_db), user=Depends(owner)):
    enforce_project_rate_limit(request, project_id=project_id, action="photos.connect", limit=5)
    try:
        result = photos.begin_oauth(db, project_id)
        audit(db, user_id=user.id, project_id=project_id, action="photos.consent_started",
              correlation_id=request.state.correlation_id, metadata={"scope": "photos_picker_readonly"})
        db.commit()
        return result
    except photos.PhotosError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/oauth/google-photos/callback", response_class=PlainTextResponse)
def photos_callback(state: str, code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    try:
        photos.finish_oauth(db, state, code, denied=bool(error))
    except photos.PhotosError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    return PlainTextResponse("Google Photos connected. Return to the local editor and refresh Google Photos status.")


@router.post("/projects/{project_id}/photos/{action}")
def photos_action(project_id: str, action: str, request: Request, db: Session = Depends(get_db), user=Depends(owner)):
    if action not in {"select", "poll", "import-next", "cancel", "disconnect", "skip"}:
        raise HTTPException(404, "Photos action not found")
    enforce_project_rate_limit(request, project_id=project_id, action=f"photos.{action}", limit=600 if action == "import-next" else 60)
    try:
        row = photos.acquire(db, project_id)
    except photos.PhotosError as exc:
        raise HTTPException(409, str(exc)) from None
    try:
        data = photos.unpack(row)
        try:
            if action == "select":
                photos.create_selection(row, data)
            elif action == "poll":
                photos.poll_selection(row, data)
            elif action == "import-next":
                photos.import_next(db, row, data)
            elif action == "cancel":
                photos.cancel_selection(row, data)
            elif action == "disconnect":
                photos.disconnect(row, data)
            elif action == "skip":
                if not data.get("error") or data.get("cursor", 0) >= len(data.get("items", [])):
                    raise photos.PhotosError("No failed item to skip")
                data["cursor"] = data.get("cursor", 0) + 1
                data["skipped"] = data.get("skipped", 0) + 1
                data.pop("error", None)
            photos.save(row, data)
        except ValueError as exc:
            # Preserve completed items even if the final Google session cleanup fails.
            data["error"] = str(exc) if isinstance(exc, photos.PhotosError) else "Media failed local scanning or format validation"
            photos.save(row, data)
        audit(db, user_id=user.id, project_id=project_id, action=f"photos.{action}",
              correlation_id=request.state.correlation_id, metadata={"status": row.status, "processed": data.get("cursor", 0)})
        db.commit()
        return photos.status(db, project_id)
    finally:
        photos.release(db, row)
