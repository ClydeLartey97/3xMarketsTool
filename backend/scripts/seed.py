from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.ingestion.seeds import seed_database


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)


if __name__ == "__main__":
    main()
