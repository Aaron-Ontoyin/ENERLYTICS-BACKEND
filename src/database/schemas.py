from datetime import datetime
from uuid import UUID as PyUUID

from pydantic import BaseModel


class TokenBlacklist(BaseModel):
    jti: str
    token_type: str
    user_id: PyUUID
    expires_at: datetime
