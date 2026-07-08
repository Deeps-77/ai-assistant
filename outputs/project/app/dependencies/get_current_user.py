from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.dependencies.get_db import db_dependency

async def get_current_user(db: Annotated[session, Depends(db_dependency)], token: str = Depends(oauth2_scheme)):
    """Get current user from token."""
    # Implement token validation logic here
    return User(id=1, username="testuser", email="test@example.com")