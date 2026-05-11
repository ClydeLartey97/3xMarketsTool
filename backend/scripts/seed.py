from app.db.schema import require_database_schema
from app.db.session import SessionLocal, engine
from app.ingestion.seeds import seed_database


def main() -> None:
    require_database_schema(engine)
    with SessionLocal() as db:
        seed_database(db)


if __name__ == "__main__":
    main()
