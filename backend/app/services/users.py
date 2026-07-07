from datetime import UTC, datetime



from sqlalchemy import delete, func, select

from sqlalchemy.orm import Session



from app.core.auth import hash_password

from app.models.entities import IdempotencyRecord, User, UserRole





def set_user_password(user: User, password: str) -> None:

    user.password_hash = hash_password(password)

    user.password_plain = password





def list_users(db: Session) -> list[User]:

    return list(db.scalars(select(User).order_by(User.email.asc())).all())





def _assert_can_disable(db: Session, user: User, *, actor: User) -> None:

    if actor.id == user.id:

        raise ValueError("You cannot disable your own account")

    if user.role == UserRole.owner:

        owner_count = db.scalar(

            select(func.count()).select_from(User).where(User.role == UserRole.owner)

        )

        if owner_count is not None and owner_count <= 1:

            raise ValueError("Cannot disable the last owner account")





def set_user_active(db: Session, user_id: int, *, actor: User, is_active: bool) -> User:

    user = db.get(User, user_id)

    if not user:

        raise ValueError("User not found")

    if not is_active:

        _assert_can_disable(db, user, actor=actor)

    if user.is_active == is_active:

        return user

    user.is_active = is_active

    db.commit()

    db.refresh(user)

    from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event



    record_audit_event(

        db,

        user=actor,

        action=AuditAction.USER_ENABLED if is_active else AuditAction.USER_DISABLED,

        entity_type=AuditEntityType.USER,

        entity_id=user.id,

        entity_label=user.email,

    )

    return user





def create_user(

    db: Session,

    *,

    actor: User,

    email: str,

    password: str,

    name: str | None,

    role: UserRole,

) -> User:

    existing = db.scalar(select(User).where(User.email == email))

    if existing:

        raise ValueError("Email already registered")

    user = User(

        email=email,

        name=name.strip() if name else None,

        role=role,

        last_login_at=None,

        is_active=True,

    )

    set_user_password(user, password)

    db.add(user)

    db.commit()

    db.refresh(user)

    from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event



    record_audit_event(

        db,

        user=actor,

        action=AuditAction.USER_CREATED,

        entity_type=AuditEntityType.USER,

        entity_id=user.id,

        entity_label=user.email,

        metadata={"role": user.role.value if user.role else None},

    )

    return user





def update_user(

    db: Session,

    user_id: int,

    *,

    actor: User,

    name: str | None = None,

    role: UserRole | None = None,

    password: str | None = None,

    is_active: bool | None = None,

) -> User:

    user = db.get(User, user_id)

    if not user:

        raise ValueError("User not found")



    if is_active is not None and user.is_active != is_active:

        if not is_active:

            _assert_can_disable(db, user, actor=actor)

        user.is_active = is_active

        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event



        record_audit_event(

            db,

            user=actor,

            action=AuditAction.USER_ENABLED if is_active else AuditAction.USER_DISABLED,

            entity_type=AuditEntityType.USER,

            entity_id=user.id,

            entity_label=user.email,

        )



    old_role = user.role

    changed_profile = False

    if name is not None:

        user.name = name.strip() if name else None

        changed_profile = True

    if role is not None:

        user.role = role

        changed_profile = True

    if password is not None:

        set_user_password(user, password)

        changed_profile = True



    if changed_profile or (is_active is not None):

        db.commit()

        db.refresh(user)



    if changed_profile:

        from app.services.audit_log import AuditAction, AuditEntityType, record_audit_event



        metadata: dict = {}

        if role is not None and role != old_role:

            metadata["role_from"] = old_role.value if old_role else None

            metadata["role_to"] = role.value

        if password is not None:

            metadata["password_changed"] = True

        record_audit_event(

            db,

            user=actor,

            action=AuditAction.USER_UPDATED,

            entity_type=AuditEntityType.USER,

            entity_id=user.id,

            entity_label=user.email,

            metadata=metadata or None,

        )

    return user





def delete_user(db: Session, user_id: int, *, actor_id: int) -> None:

    if user_id == actor_id:

        raise ValueError("You cannot delete your own account")



    user = db.get(User, user_id)

    if not user:

        raise ValueError("User not found")



    if user.role == UserRole.owner:

        owner_count = db.scalar(

            select(func.count()).select_from(User).where(User.role == UserRole.owner)

        )

        if owner_count is not None and owner_count <= 1:

            raise ValueError("Cannot delete the last owner account")



    db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id))

    db.delete(user)

    db.commit()

