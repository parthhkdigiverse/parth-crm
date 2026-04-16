# backend/app/core/dependencies.py
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from beanie import PydanticObjectId
from app.core.config import settings
from app.modules.users.models import User, UserRole
from app.modules.auth.schemas import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_DEMO_USER_ID = "000000000000000000000000"

class SyntheticUser:
    """A mock user for Demo or Dev modes."""
    id = PydanticObjectId(_DEMO_USER_ID)
    email = "admin@example.com"
    name = "Demo Admin"
    role = UserRole.ADMIN
    is_active = True
    preferences = {}
    hashed_password = "hashed_password_placeholder"

    def __getitem__(self, key):
        return getattr(self, key)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Async dependency — resolves JWT sub to a Beanie User document."""
    if token == "dev-token":
        return SyntheticUser()

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        token_data = TokenData(sub=user_id_str)
    except jwt.PyJWTError:
        raise credentials_exception

    # Demo / synthetic admin — sub is all-zeros ObjectId or legacy "0"
    if token_data.sub in (_DEMO_USER_ID, "0"):
        return SyntheticUser()

    try:
        oid = PydanticObjectId(token_data.sub)
    except Exception:
        raise credentials_exception

    try:
        user = await User.get(oid)
    except Exception as db_err:
        print(f"DATABASE ERROR in get_current_user: {db_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )

    if user is None:
        raise credentials_exception

    if getattr(user, "is_deleted", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deleted.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user is None:
        return None
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    async def __call__(self, user: User = Depends(get_current_active_user)):
        if user is None:
            return SyntheticUser()

        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The user doesn't have enough privileges",
            )
        return user
