from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.idempotency import require_idempotency_key, run_idempotent_mutation
from app.core.permissions import Permission, require_permission
from app.core.tenant import company_id_for_user, require_entity_company
from app.database import get_db
from app.models.entities import User, UserRole
from app.schemas import LoginOtpOut, UserAdminOut, UserCreate, UserUpdate
from app.services.idempotency import hash_pydantic_body
from app.services.login_otp import generate_login_otp
from app.services.users import create_user, delete_user, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


def _user_admin_out(user: User) -> UserAdminOut:
    role = user.role.value if user.role else None
    return UserAdminOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        role=role,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        password=user.password_plain,
        is_active=user.is_active,
    )


@router.get("", response_model=list[UserAdminOut])
def get_users(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
):
    return [_user_admin_out(u) for u in list_users(db, company_id=company_id_for_user(actor))]


@router.post("", response_model=UserAdminOut, status_code=201)
def post_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
    idempotency_key: str = Depends(require_idempotency_key),
):
    route_key = "POST /api/users"
    request_hash = hash_pydantic_body(body)

    def execute():
        try:
            user = create_user(
                db,
                actor=actor,
                email=body.email,
                password=body.password,
                name=body.name,
                role=UserRole(body.role),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return _user_admin_out(user), 201

    return run_idempotent_mutation(db, actor, idempotency_key, route_key, request_hash, execute)


@router.patch("/{user_id}", response_model=UserAdminOut)
def patch_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
):
    try:
        user = update_user(
            db,
            user_id,
            actor=actor,
            name=body.name,
            role=UserRole(body.role) if body.role is not None else None,
            password=body.password,
            is_active=body.is_active,
        )
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e).lower() else 400, str(e)) from e
    return _user_admin_out(user)


@router.delete("/{user_id}", status_code=204)
def remove_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
):
    try:
        delete_user(db, user_id, actor=actor)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(404, msg) from e
        raise HTTPException(400, msg) from e
    return None


@router.post("/{user_id}/login-otp", response_model=LoginOtpOut)
def post_login_otp(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
):
    user = db.get(User, user_id)
    require_entity_company(user, company_id_for_user(actor), label="User")
    code, expires_at = generate_login_otp(db, user)
    return LoginOtpOut(
        otp=code,
        expires_at=expires_at,
        user_email=user.email,
        user_name=user.name,
    )
