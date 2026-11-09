"""Initialise only the explicitly configured, separate managed evaluation DB.

Database/role must already exist. Never drops tables, resets or copies office
customer data, destinations, user accounts, credentials or recordings.
"""
from brightwater.db import Base
from brightwater.managed.engine import lab_engine
from brightwater.seed import seed
from sqlalchemy.orm import Session

engine = lab_engine()  # validates the dedicated database name before any DDL
Base.metadata.create_all(engine)
with Session(engine) as db, db.begin():
    created = seed(db)
print("Managed evaluation schema ready; fictional fixtures added:", created)
