"""
Aggregates all route modules into a single APIRouter mounted by main.py.

Future steps add routers here (auth, business, ai_assistant, forecasting,
simulator, etc.) without touching main.py.
"""
from fastapi import APIRouter

from app.api.routes import alerts, analytics, assistant, auth, branches, business, chat, google_integration, health, imports, simulations, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(business.router)
api_router.include_router(branches.router)
api_router.include_router(imports.router)
api_router.include_router(transactions.router)
api_router.include_router(analytics.router)
api_router.include_router(chat.router)
api_router.include_router(assistant.router)
api_router.include_router(simulations.router)
api_router.include_router(alerts.router)
api_router.include_router(google_integration.router)
api_router.include_router(google_integration.callback_router)
