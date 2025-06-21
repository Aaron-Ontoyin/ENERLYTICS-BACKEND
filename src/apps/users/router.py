from datetime import datetime
from typing import Dict, Literal, Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy.exc

from src.database import aget_db
from src.database.models import TokenBlacklist as TokenBlacklistDB
from src.database.schemas import TokenBlacklist
from src.database.pagination import PageParams, PaginatedResponse
from src.core.auth import AuthService, TokenPair, AccessToken
from src.core.dependencies import get_current_user, CurrentUser
from src.core.dependencies import get_current_user_refresh, get_page_params
from src.core.query_parser import parse_filters, build_search_filters
from .models import User as UserDB
from .schemas import LoginRequest, AccessTokenRefreshRequest, User, UserCreate, UserType
from src.database import Filter

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=User)
async def current_user(current_user: CurrentUser = Depends(get_current_user)):
    return current_user.db_user


@router.get("/users", response_model=PaginatedResponse[User])
async def get_users(
    request: Request,
    page_params: PageParams = Depends(get_page_params),
    db: AsyncSession = Depends(aget_db),
    current_user: CurrentUser = Depends(get_current_user),
    search: Optional[str] = Query(
        None, description="Search across email, first_name, and last_name"
    ),
):
    """
    Get all users with flexible filtering. Only accessible by admin users.

    ## Simple Usage:
    - `?email=john@example.com` - Exact email match
    - `?type=admin` - Filter by user type
    - `?search=john` - Search across multiple fields

    ## Advanced Filtering (field__operator=value):
    - `?email__ilike=%john%` - Case-insensitive partial match
    - `?type__in=admin,user` - Multiple values (comma-separated)
    - `?created_at__gte=2024-01-01` - Date greater than or equal
    - `?id__not_in=uuid1,uuid2` - Exclude specific IDs
    - `?first_name__like=John%` - Case-sensitive starts with
    - `?created_at__between=2024-01-01,2024-12-31` - Date range

    ## Supported Operators:
    `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not in`, `is`, `is not`,
    `like`, `ilike`, `between`, `not between`

    ## Examples:
    - `?email__ilike=john&type=admin` - Admin users with 'john' in email
    - `?created_at__between=2024-01-01,2024-12-31` - Users created in 2024
    - `?type__in=admin,user&email__not_in=test@example.com` - Complex filtering
    - `?first_name__ilike=john&last_name__ilike=doe` - Multiple field filtering
    """
    if current_user.db_user.type != UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can access this endpoint",
        )

    query_params = dict(request.query_params)
    allowed_fields = [
        "id",
        "email",
        "first_name",
        "last_name",
        "other_names",
        "phone",
        "type",
        "created_at",
        "updated_at",
    ]
    filters: List[Filter] = parse_filters(query_params, allowed_fields)

    search_filters: List[Filter] = []
    if search:
        search_filters.extend(
            build_search_filters(search, ["email", "first_name", "last_name"])
        )

    users = await UserDB.list(db, filters, search_filters, page_params)
    return PaginatedResponse[User](
        items=[User.model_validate(user, from_attributes=True) for user in users.items],
        **users.model_dump(exclude={"items"}),
    )


@router.post("/register", response_model=User)
async def register(register_data: UserCreate, db: AsyncSession = Depends(aget_db)):
    hashed_key = AuthService.get_password_hash(register_data.key)
    try:
        user = await UserDB.create(
            db,
            {
                **register_data.model_dump(exclude={"key", "key_confirm"}),
                "hashed_key": hashed_key,
            },
        )
    except sqlalchemy.exc.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists",
        )
    return user


@router.post("/login", response_model=TokenPair)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(aget_db)):
    user = await UserDB.get_one_or_none(
        db,
        Filter(field="email", operator="==", value=login_data.email),
    )
    if not user or not AuthService.verify_password(login_data.key, user.hashed_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return AuthService.create_token_pair(str(user.id))


@router.post("/refresh", response_model=AccessToken)
async def refresh_access_token(
    refresh_data: AccessTokenRefreshRequest, db: AsyncSession = Depends(aget_db)
):
    payload = await AuthService.verify_refresh_token(refresh_data.refresh_token, db)
    return AuthService.create_access_token(user_id=payload["user_id"])


@router.post(
    "/logout-refresh",
    response_model=Dict[Literal["message"], Literal["success"]],
)
async def logout_refresh(
    current_user: CurrentUser = Depends(get_current_user_refresh),
    db: AsyncSession = Depends(aget_db),
):
    if current_user.payload["type"] != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token type",
        )

    await TokenBlacklistDB.get_or_create(
        db,
        obj_in=TokenBlacklist(
            jti=current_user.payload["jti"],
            token_type="refresh",
            user_id=current_user.db_user.id,
            expires_at=datetime.fromtimestamp(current_user.payload["exp"]),
        ),
        identifier="jti",
    )

    return {"message": "success"}


@router.post(
    "/logout-access",
    response_model=Dict[Literal["message"], Literal["success"]],
)
async def logout_access(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(aget_db),
):
    await TokenBlacklistDB.get_or_create(
        db,
        obj_in=TokenBlacklist(
            jti=current_user.payload["jti"],
            token_type="access",
            user_id=current_user.db_user.id,
            expires_at=datetime.fromtimestamp(current_user.payload["exp"]),
        ),
        identifier="jti",
    )

    return {"message": "success"}
