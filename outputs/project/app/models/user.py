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