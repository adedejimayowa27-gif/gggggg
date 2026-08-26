"""
Aggregates all route modules into a single APIRouter mounted by main.py.

Future steps add routers here (auth, business, ai_assistant, forecasting,
simulator, etc.) without touching main.py.
"""
from fastapi import APIRouter

from app.api.routes import auth, business, health, imports

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(business.router)
api_router.include_router(imports.router)
