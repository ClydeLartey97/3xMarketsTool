from collections.abc import Generator
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_threex.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.ingestion.seeds import seed_database
from app.main import app
from app.models import User
from app.services.auth import create_access_token, hash_password


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_threex.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TEST_USER_EMAIL = "test@3x.local"
TEST_USER_PASSWORD = "test-password"


@pytest.fixture(autouse=True)
def setup_db() -> Generator[None, None, None]:
    limiter.limiter.storage.reset()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as db:
        seed_database(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def auth_user(db_session: Session) -> User:
    user = db_session.scalar(select(User).where(User.email == TEST_USER_EMAIL))
    if user:
        return user
    user = User(
        email=TEST_USER_EMAIL,
        password_hash=hash_password(TEST_USER_PASSWORD),
        organisation="3x Test",
        role="analyst",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(auth_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(auth_user)}"}


@pytest.fixture
def anon_client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client(anon_client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    anon_client.headers.update(auth_headers)
    return anon_client
