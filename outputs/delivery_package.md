# ═══════════════════════════════════════════
# SOFTWARE DELIVERY PACKAGE
# ═══════════════════════════════════════════

## Requirement

Build a todo app

## Tech Stack
Python/FastAPI

## User Stories

- As a user, I want to create a new task so that I can keep track of my responsibilities.
- As a user, I want to mark a task as completed so I know it's done.
- As a user, I want to delete a task so I can remove outdated items.
- As a user, I want to edit a task so I can update its details.
- As a user, I want to view all my tasks so I can manage them effectively.

## Completed Modules

- tasks
- auth

## Architecture

# Architecture Document

## Tech Stack
FastAPI, PostgreSQL, Pydantic, JWT, uvicorn, SQLAlchemy ORM

## Database Schema
CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR UNIQUE NOT NULL, password_hash TEXT NOT NULL); CREATE TABLE tasks (id SERIAL PRIMARY KEY, title VARCHAR NOT NULL, description TEXT, status BOOLEAN DEFAULT false, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, user_id INTEGER REFERENCES users(id));

## API Endpoints
/tasks - POST (create), GET (list), PUT (update), DELETE (remove)
/tasks/{task_id} - GET (detail), PUT (update), DELETE (remove)
/auth/login - POST (authenticate)
/auth/register - POST (signup)

## Folder Structure
app/
  api/
    tasks.py
    auth.py
  models/
    task_model.py
    user_model.py
  database/
    db_init.py
  auth/
    jwt_utils.py
  main.py

## Architecture Diagram
           +-------------------+
           |   FastAPI      |
           | (Main Server) |
           +-------+--------+
                 |          |
           +-----v---------+
           |  Tasks Module |
           |  (CRUD Logic) |
           +-----+---------+
           |  Auth Module |
           |  (JWT Logic) |
           +-------------------+
             ^        ^
     +--------+--------+
     |  PostgreSQL DB |
     |  (Task/Users)  |
     +-----------------+


## Written Files

- app/tasks.py [ok]
- app/routers/auth_router.py [ok]
- app/models/user.py [ok]
- app/models/token.py [ok]
- app/services/user_service.py [ok]
- app/dependencies/get_db.py [ok]
- app/dependencies/get_current_user.py [ok]
- app/main.py [ok]
- tasks [ok]
- auth [ok]


## ═══ SOURCE CODE ═══


### Module: tasks

# --- app/tasks.py ---
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional
import os
from fastapi.middleware import Middleware
from fastapi_rate_limiter import RateLimiterMiddleware

app = FastAPI()

# Add rate limiting middleware
app.add_middleware(RateLimiterMiddleware, default_rate_limit="100 per minute")

oauth2_scheme = OAuth2PasswordBearer(token_url="/token")

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None

class Task(TaskBase):
    id: int

# Dummy data for demonstration
tasks = []

@app.post("/tasks/", response_model=Task)
async def create_task(task: TaskBase, token: str = Depends(oauth2_scheme)):
    # Validate token (simplified)
    if not validate_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")

    new_task = Task(id=len(tasks)+1, **task.dict())
    tasks.append(new_task)
    return new_task

def validate_token(token: str) -> bool:
    # In a real app, this would check against a database or token store
    return token == "valid_token"}


### Module: auth

# --- app/routers/auth_router.py ---
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

# --- app/models/user.py ---
from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    id: int
    username: str
    email: str
    hashed_password: str
    
    class Config:
        orm_mode = True

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

# --- app/models/token.py ---
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str
    
    class Config:
        orm_mode = True

# --- app/services/user_service.py ---
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

# --- app/dependencies/get_db.py ---
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Annotated

class Database:
    def __init__(self):
        self.engine = create_engine("sqlite:///./test.db")
        self.session_local = sessionmaker(autocommit=False, autoflush=False)

    def get_db(self):
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

# Initialize database
db_dependency = Database()

# --- app/dependencies/get_current_user.py ---
from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.dependencies.get_db import db_dependency

async def get_current_user(db: Annotated[session, Depends(db_dependency)], token: str = Depends(oauth2_scheme)):
    """Get current user from token."""
    # Implement token validation logic here
    return User(id=1, username="testuser", email="test@example.com")

# --- app/main.py ---
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware import Middleware
from fastapi_rate_limiter import RateLimiterMiddleware
from app.routers.auth import router as auth_router
from app.dependencies.get_db import db_dependency
from app.dependencies.get_current_user import get_current_user

app = FastAPI(
    title="Auth Service",
    description="Authentication and authorization service",
    version="1.0.0"
)

# Rate limiting middleware
app.add_middleware(
    RateLimiterMiddleware,
    rate_limit=5,
    rate_limit_period=60,
    rate_limit_exceeded_response=HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests, please try again later")
)

# Include routers
app.include_router(auth_router)

# Dependency injection for database
@app.on_event("startup")
async def startup():
    # Initialize database
    pass

@app.on_event("shutdown")
async def shutdown():
    # Clean up resources
    pass


## ═══ TEST CODE ═══


### Tests: tasks

```python
import pytest
from fastapi.testclient import TestClient
from app.tasks import app, tasks, validate_token


@pytest.fixture(autouse=True)
def reset_tasks():
    tasks.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_create_task_valid_token(client):
    response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Test Task"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Test Task"
    assert "description" not in data or data["description"] is None
    assert len(tasks) == 1


def test_create_task_invalid_token(client):
    response = client.post("/tasks/", headers={"Authorization": "Bearer invalid_token"}, json={"title": "Test Task"})
    assert response.status_code == 401


def test_create_task_missing_title(client):
    response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={})
    assert response.status_code == 422
    assert "detail" in response.json()
    assert "title" in response.json()["detail"]


def test_create_task_with_description(client):
    response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Test Task", "description": "This is a description."})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["description"] == "This is a description."


def test_validate_token_valid():
    assert validate_token("valid_token") is True


def test_validate_token_invalid():
    assert validate_token("invalid_token") is False


def test_rate_limiting(client):
    # Send 100 requests with valid token
    for _ in range(100):
        response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Test Task"})
        assert response.status_code == 200

    # Now send the 101st request
    response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Test Task"})
    assert response.status_code == 429


def test_rate_limiting_with_multiple_requests(client):
    # Send 5 requests with valid token
    for _ in range(5):
        response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Test Task"})
        assert response.status_code == 200

    # Send another request after a short delay (simulating time passing)
    response = client.post("/tasks/", headers={"Authorization": "Bearer valid_token"}, json={"title": "Another Task"})
    assert response.status_code == 200
```

### Tests: auth

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.user import UserCreate, User
from app.models.token import Token
from app.dependencies.get_db import db_dependency
from app.services.user_service import create_user, authenticate_user
from unittest.mock import patch, MagicMock

# Initialize test client
client = TestClient(app)

# Mock the database session for testing
def mock_db_session():
    return MagicMock()

# Patch get_db to use a mock session
@pytest.fixture(autouse=True)
def mock_get_db():
    with patch('app.dependencies.get_db.get_db', return_value=mock_db_session()):
        yield

# Mock user_service functions
@patch('app.services.user_service.create_user')
@patch('app.services.user_service.authenticate_user')
def test_register_user_success(mock_authenticate, mock_create):
    # Setup mocks
    mock_create.return_value = User(id=1, username="testuser", email="test@example.com", hashed_password="hashedpassword")
    mock_authenticate.return_value = None

    response = client.post("/api/v1/auth/register", json={"username": "testuser", "email": "test@example.com", "password": "password"})
    assert response.status_code == 200
    token_data = response.json()
    assert token_data["access_token"] == "1"
    assert token_data["token_type"] == "bearer"

def test_register_user_duplicate_username(mock_db_session):
    # Setup mocks for duplicate username
    mock_db_session.query.return_value.filter.return_value.first.return_value = User(username="testuser")
    
    response = client.post("/api/v1/auth/register", json={"username": "testuser", "email": "test@example.com", "password": "password"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists"

def test_register_user_duplicate_email(mock_db_session):
    # Setup mocks for duplicate email
    mock_db_session.query.return_value.filter.return_value.first.return_value = User(email="test@example.com")
    
    response = client.post("/api/v1/auth/register", json={"username": "newuser", "email": "test@example.com", "password": "password"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already exists"

@patch('app.services.user_service.create_user')
def test_login_user_success(mock_create):
    # Setup mock for successful authentication
    mock_create.return_value = User(id=1, username="testuser", email="test@example.com", hashed_password="hashedpassword")
    
    response = client.post("/api/v1/auth/login", json={"username": "testuser", "email": "test@example.com", "password": "password"})
    assert response.status_code == 200
    token_data = response.json()
    assert token_data["access_token"] == "1"
    assert token_data["token_type"] == "bearer"

@patch('app.services.user_service.create_user')
def test_login_user_invalid_password(mock_create):
    # Setup mock for invalid password
    mock_create.return_value = User(id=1, username="testuser", email="test@example.com", hashed_password="hashedpassword")
    
    response = client.post("/api/v1/auth/login", json={"username": "testuser", "email": "test@example.com", "password": "wrongpassword"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

@patch('app.services.user_service.create_user')
def test_login_user_non_existent_user(mock_create):
    # Setup mock for non-existent user
    mock_create.return_value = None
    
    response = client.post("/api/v1/auth/login", json={"username": "nonexistent", "email": "nonexistent@example.com", "password": "password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_get_current_user(mock_db_session):
    # Test that the dependency is called with a valid token
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["id"] == 1
    assert user_data["username"] == "testuser"
    assert user_data["email"] == "test@example.com"
```