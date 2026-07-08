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