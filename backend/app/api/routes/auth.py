"""Authentication, account lifecycle and session management endpoints."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from jwt.exceptions import PyJWTError as JWTError

from app.api.deps import enforce_rate_limit, get_app_settings, get_current_user, get_repositories
from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_email_token,
    create_refresh_token,
    decode_token,
    hash_password,
    utcnow,
    verify_password,
)
from app.db.repositories import Repositories, public
from app.schemas import (
    ForgotPasswordRequest,
    LoginSecurityOut,
    RefreshRequest,
    ResetPasswordRequest,
    SigninEventOut,
    TokenPair,
    UserLogin,
    UserOut,
    UserRegister,
    VerifyEmailRequest,
)
from app.services.login_security import (
    device_hash,
    device_label,
    signin_event_out,
    signin_summary,
)
from app.services.notification_service import NotificationService
from app.services.plan_service import PlanService
from app.services.turnstile_service import verify_turnstile_token

router = APIRouter(prefix="/auth", tags=["authentication"])


def _user_out(document: dict[str, Any]) -> UserOut:
    data = public(document) or {}
    return UserOut(
        id=str(data["id"]),
        email=data["email"],
        full_name=data.get("full_name", ""),
        role=data.get("role", "user"),
        organisation=data.get("organisation"),
        email_verified=bool(data.get("email_verified")),
        created_at=data["created_at"],
        preferences=data.get("preferences", {}),
    )


def _notification_service(settings: Settings, repos: Repositories) -> NotificationService:
    return NotificationService(settings, repos)


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _cloudflare_country(request: Request) -> str | None:
    """Use Cloudflare's edge header when present; no external geo lookup is made."""
    value = request.headers.get("cf-ipcountry")
    if value and value.upper() not in {"XX", "T1"}:
        return value[:2].upper()
    return None


def _verification_message(status_value: str) -> str:
    return {
        "missing_token": "Security verification is required. Please try again.",
        "verification_unavailable": "Security verification is temporarily unavailable. Please try again shortly.",
        "hostname_mismatch": "Security verification failed for this site. Please reload and try again.",
    }.get(status_value, "Security verification failed. Please try again.")


@router.get("/security-config", response_model=LoginSecurityOut)
def security_config(settings: Settings = Depends(get_app_settings)) -> LoginSecurityOut:
    """Public, non-secret login verification capabilities for the sign-in form."""
    if settings.turnstile_active:
        return LoginSecurityOut(
            enabled=True,
            site_key=settings.turnstile_site_key,
            status="configured",
            note="Protected by Cloudflare Turnstile.",
        )
    return LoginSecurityOut(
        enabled=False,
        site_key=None,
        status="not_configured",
        note="Cloudflare Turnstile is not configured on this deployment.",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    _: None = Depends(enforce_rate_limit),
) -> UserOut:
    email = payload.email.lower().strip()
    if repos.users.get_by_email(email):
        raise HTTPException(status_code=409, detail="an account with this email already exists")
    user = repos.users.create(
        {
            "email": email,
            "password_hash": hash_password(payload.password),
            "full_name": payload.full_name.strip(),
            "organisation": payload.organisation.strip() if payload.organisation else None,
            "role": "user",
            "active": True,
            "email_verified": False,
            "created_at": utcnow(),
            "preferences": {"email_alerts": True, "in_app_alerts": True, "sms_alerts": False},
            "consent": {"privacy": True, "terms": True, "recorded_at": utcnow()},
        }
    )
    PlanService(settings, repos).ensure_subscription(str(user["_id"]))
    repos.audit.log(str(user["_id"]), "user.registered", ip=request.client.host if request.client else None)

    token = create_email_token(settings, str(user["_id"]), "verify_email")
    verify_link = f"{settings.cors_origins[0]}/verify-email?token={token}"
    _notification_service(settings, repos).send_email(
        email,
        "Verify your TrustLens AI account",
        f"Verify your email address: {verify_link}",
    )
    return _user_out(user)


@router.post("/login", response_model=TokenPair)
def login(
    payload: UserLogin,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    _: None = Depends(enforce_rate_limit),
) -> TokenPair:
    user = repos.users.get_by_email(payload.email.lower().strip())
    if not user or not verify_password(payload.password, str(user.get("password_hash"))):
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="account is disabled")

    user_id = str(user["_id"])
    client_ip = _request_ip(request)
    role = str(user.get("role", "user"))
    is_admin = role in {"admin", "owner"}
    if payload.access_mode == "admin" and not is_admin:
        repos.audit.log(
            user_id,
            "user.login_rejected",
            metadata={"reason": "access_mode", "requested": "admin", "role": role},
            ip=client_ip,
        )
        raise HTTPException(status_code=403, detail="this account does not have administrator access")
    if payload.access_mode == "user" and is_admin:
        repos.audit.log(
            user_id,
            "user.login_rejected",
            metadata={"reason": "access_mode", "requested": "user", "role": role},
            ip=client_ip,
        )
        raise HTTPException(status_code=403, detail="use Administrator sign in for this account")

    verification = verify_turnstile_token(settings, payload.turnstile_token, client_ip)
    if verification["enabled"] and not verification["success"]:
        repos.audit.log(
            user_id,
            "user.login_rejected",
            metadata={"reason": "turnstile", "verification": verification["status"]},
            ip=client_ip,
        )
        raise HTTPException(status_code=400, detail=_verification_message(verification["status"]))

    previous = repos.signins.latest(user_id)
    device_id = payload.device_id or secrets.token_urlsafe(24)
    hash_value = device_hash(settings, device_id) if payload.remember_device else None
    known_device = bool(hash_value and repos.signins.known_device(user_id, hash_value))
    new_device = previous is not None and not known_device
    event = repos.signins.insert(
        {
            "user_id": user_id,
            "created_at": utcnow(),
            "device_label": device_label(request.headers.get("user-agent")),
            "device_hash": hash_value,
            "known_device": known_device,
            "ip": client_ip,
            "country": _cloudflare_country(request),
            "verification": verification["status"],
        }
    )
    repos.audit.log(
        user_id,
        "user.login",
        metadata={
            "device": event["device_label"],
            "new_device": new_device,
            "device_remembered": bool(hash_value),
            "verification": verification["status"],
        },
        ip=client_ip,
    )
    if new_device:
        location = f" ({event['country']})" if event.get("country") else ""
        _notification_service(settings, repos).notify(
            user_id=user_id,
            user_email=str(user.get("email")),
            kind="new_device_signin",
            title="New sign-in on your TrustLens account",
            body=(
                f"A sign-in from {event['device_label']}{location} was not a recognised device. "
                "If this was not you, change your password immediately."
            ),
            severity="medium",
            dedupe_key=f"new_device:{event['_id']}",
            send_email=True,
        )
    return TokenPair(
        access_token=create_access_token(settings, user_id, role),
        refresh_token=create_refresh_token(settings, user_id),
        expires_in=settings.access_token_expire_minutes * 60,
        device_id=device_id,
        previous_signin=signin_summary(previous) if previous else None,
        new_device=new_device,
        verification=verification["status"],
    )


@router.get("/signin-activity", response_model=list[SigninEventOut])
def signin_activity(
    limit: int = Query(default=10, ge=1, le=50),
    user: dict[str, Any] = Depends(get_current_user),
    repos: Repositories = Depends(get_repositories),
) -> list[SigninEventOut]:
    """Recent sign-ins for the authenticated account owner only."""
    return [signin_event_out(event) for event in repos.signins.for_user(str(user["id"]), limit=limit)]


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> TokenPair:
    try:
        claims = decode_token(settings, payload.refresh_token, expected_type="refresh")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = repos.users.get(str(claims.get("sub")))
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="user unavailable")
    user_id = str(user["_id"])
    return TokenPair(
        access_token=create_access_token(settings, user_id, str(user.get("role", "user"))),
        refresh_token=create_refresh_token(settings, user_id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    if authorization and " " in authorization:
        token = authorization.split(" ", 1)[1]
        try:
            claims = decode_token(settings, token, expected_type="access")
            repos.blacklist.insert({"jti": claims.get("jti"), "created_at": utcnow()})
        except (ValueError, JWTError):
            pass
    repos.audit.log(str(user["id"]), "user.logout")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
def me(user: dict[str, Any] = Depends(get_current_user)) -> UserOut:
    return UserOut(**user)


@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, str]:
    try:
        claims = decode_token(settings, payload.token, expected_type="verify_email")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = repos.users.get(str(claims.get("sub")))
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repos.users.set_verified(str(user["_id"]))
    repos.audit.log(str(user["_id"]), "user.email_verified")
    return {"status": "verified"}


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    _: None = Depends(enforce_rate_limit),
) -> dict[str, str]:
    user = repos.users.get_by_email(payload.email.lower().strip())
    if user:
        token = create_email_token(settings, str(user["_id"]), "password_reset")
        link = f"{settings.cors_origins[0]}/reset-password?token={token}"
        _notification_service(settings, repos).send_email(
            str(user["email"]), "Reset your TrustLens AI password", f"Reset your password: {link}"
        )
        repos.audit.log(str(user["_id"]), "user.password_reset_requested")
    return {"status": "accepted"}


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, str]:
    try:
        claims = decode_token(settings, payload.token, expected_type="password_reset")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = repos.users.get(str(claims.get("sub")))
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repos.users.update(
        str(user["_id"]),
        {"password_hash": hash_password(payload.new_password), "password_changed_at": utcnow()},
    )
    repos.audit.log(str(user["_id"]), "user.password_reset_completed")
    return {"status": "updated"}


@router.post("/resend-verification")
def resend_verification(
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    token = create_email_token(settings, str(user["id"]), "verify_email")
    link = f"{settings.cors_origins[0]}/verify-email?token={token}"
    _notification_service(settings, repos).send_email(
        str(user["email"]), "Verify your TrustLens AI account", f"Verify your email address: {link}"
    )
    return {"status": "accepted"}
