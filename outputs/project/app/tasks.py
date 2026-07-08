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