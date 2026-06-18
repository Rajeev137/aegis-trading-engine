from datetime import datetime, timezone, timedelta
from typing import Any, Union
import jwt
from passlib.context import CryptContext
from app.core.config import settings

#Bcrypt context for hashing passwords
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a password using bcrypt_sha256 for arbitrary length input."""
    return pwd_context.hash(password)
def create_access_token(subject: Union[str, Any]) -> str:
    """Creates a JWT access token"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    #'sub' is a standard JWT claim for the user identifier
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

