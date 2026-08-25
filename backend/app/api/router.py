"""
Aggregates all route modules into a single APIRouter mounted by main.py.

Future steps add routers here (auth, business, ai_assistant, forecasting,
simulator, etc.) without touching main.py.
"""
from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
