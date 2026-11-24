from alembic import context

from app import models
from app.config import DATABASE_URL
from app.db import engine

metadata = models.Base.metadata

if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (connection := context.config.attributes.get("connection")) is not None:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
