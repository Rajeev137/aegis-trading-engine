from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.db.models import User
from app.api import schemas
from app.core import security
from app.core.config import settings

router = APIRouter()

@router.post("/register", response_model = schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    """Registers a new user with email and password"""
    #hash the password
    hashed_password = security.get_password_hash(user_in.password)
    
    #create the sqlalchemy user model instance
    new_user = User(email=user_in.email, password_hash=hashed_password)
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)
        return new_user
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

@router.post("/login", response_model = schemas.TokenResponse)
async def login_user(user_in: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Logs in a user and returns a JWT access token"""
    #fetch the user by email
    query  = select(User).where(User.email == user_in.username)
    result = await db.execute(query)
    user = result.scalars().first()

    #verify user exists and password is correct
    if not user or not security.verify_password(user_in.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"},)
    
    #generate JWT token
    access_token = security.create_access_token(subject=str(user.id))

    return schemas.TokenResponse(
        access_token=access_token,
        expires_at = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
