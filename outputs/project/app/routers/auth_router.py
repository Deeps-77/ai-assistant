from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from app.models.user import User
from app.models.token import Token
from app.services.user_service import create_user, authenticate_user
from app.dependencies.get_db import get_db
from fastapi.security.oauth2 import OAuth2PasswordBearer
from app.dependencies.get_current_user import get_current_user
from app.models.user import UserCreate
import bcrypt

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

@router.post("/register", response_model=Token)
async def register_user(user: UserCreate, db: Annotated[session, Depends(get_db)]):
    """Register a new user."""
    try:
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
        new_user = create_user(db=db, username=user.username, email=user.email, password=hashed_password)
        return Token(access_token=new_user.id, token_type="bearer")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", response_model=Token)
async def login_user(user: UserCreate, db: Annotated[session, Depends(get_db)]):
    """Login an existing user."""
    try:
        user_data = authenticate_user(db=db, username=user.username, password=user.password)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return Token(access_token=user_data.id, token_type="bearer")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me", response_model=User)
async def get_current_user(current_user: Annotated[User, Depends(get_current_user)]):
    """Get current user information."""
    return current_user