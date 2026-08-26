from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException

from .settings import settings


@dataclass(frozen=True)
class User:
    uid: str


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    x_bling_token: Annotated[str | None, Header()] = None,
) -> User:
    """Verify Firebase anonymously-authenticated users in production.

    Local development remains frictionless when no Firebase project is configured.
    """
    if not settings.firebase_project_id:
        return User("local-owner")
    if (not authorization or not authorization.startswith("Bearer ")) and x_bling_token:
        authorization = "Bearer " + x_bling_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail={"code": "auth_required", "message": "私有衣橱身份已失效，请刷新页面。"})
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": settings.firebase_project_id})
        token = auth.verify_id_token(authorization[7:], check_revoked=True)
        uid = token.get("uid") or token.get("sub")
        if not uid:
            raise ValueError("missing uid")
        return User(str(uid))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, detail={"code": "invalid_auth", "message": "私有衣橱身份验证失败。"}) from exc
