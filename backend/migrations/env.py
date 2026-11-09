from alembic import context

from brightwater import models  # noqa: F401
from brightwater.db import Base, engine

if context.is_offline_mode():
    from brightwater.config import settings
    context.configure(url=settings().database_url.get_secret_value(), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
