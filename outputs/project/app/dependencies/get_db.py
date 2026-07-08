from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Annotated

class Database:
    def __init__(self):
        self.engine = create_engine("sqlite:///./test.db")
        self.session_local = sessionmaker(autocommit=False, autoflush=False)

    def get_db(self):
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

# Initialize database
db_dependency = Database()