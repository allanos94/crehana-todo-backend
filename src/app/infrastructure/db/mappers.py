"""ORM <-> domain mapping functions.

Domain objects are plain dataclasses, never ORM instances, so lazy loading
is structurally impossible once a row crosses this boundary (design ADR-07).
"""

from app.domain.user import User
from app.infrastructure.db.models import UserModel


def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        email=user.email,
        hashed_password=user.hashed_password,
        created_at=user.created_at,
    )


def model_to_user(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        hashed_password=model.hashed_password,
        created_at=model.created_at,
    )
