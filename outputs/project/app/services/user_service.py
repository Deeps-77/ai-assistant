from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Annotated, Optional
import bcrypt

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    hashed_password = Column(String)

engine = create_engine("sqlite:///./test.db")
db_session = sessionmaker(autocommit=False, autoflush=False)(engine)

def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()

def create_user(db: Annotated[session, Depends(get_db)], username: str, email: str, password: str):
    """Create a new user in the database."""
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    db_email = db.query(User).filter(User.email == email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    new_user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

async def authenticate_user(db: Annotated[session, Depends(get_db)], username: str, password: str):
    """Authenticate a user."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    
    if bcrypt.checkpw(password.encode('utf-utf-8'), user.hashed_password.encode('utf-8')):
        return user
    return None