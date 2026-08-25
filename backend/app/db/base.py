"""
Single import point for all ORM models.

Alembic's env.py imports this module so that `Base.metadata` is aware of
every model when autogenerating migrations. When a new model file is added
under app/models/, import it here too.

NOTE: No models yet -- User and Business models are added in the next
build step. This file exists now so the import path is stable.
"""
from app.db.base_class import Base  # noqa: F401

# Models will be imported here as they're created, e.g.:
# from app.models.user import User  # noqa: F401
# from app.models.business import Business  # noqa: F401
