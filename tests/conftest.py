import uuid

import pytest
import resend

import app.routers.transactions as transactions_router
import app.services.log_service as log_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.config import get_settings
from app.models.category import Category, CategoryType
import app.main as main_module

# Background jobs use the real database and call Flutterwave, so keep them out of tests
main_module.start_scheduler = lambda: None

settings = get_settings()

# Use a separate test database
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/viciniti", "/viciniti_test"
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

# log_event() opens its own sessions; make it write to the test database, not the real one
log_service.session_factory = TestingSessionLocal

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables before tests, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def clean_tables():
    """Clear all tables between tests so they don't interfere."""
    yield
    db = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

@pytest.fixture(autouse=True)
def sent_emails(monkeypatch):
    """Record emails instead of sending them through Resend; tests can inspect the list."""
    sent = []

    def fake_send(params):
        sent.append(params)
        return {"id": f"test-email-{len(sent)}"}

    monkeypatch.setattr(resend.Emails, "send", staticmethod(fake_send))
    return sent

def _create_category(type_: CategoryType) -> str:
    db = TestingSessionLocal()
    category = Category(name=f"Test {type_.value}", slug=f"test-{type_.value}-{uuid.uuid4().hex[:6]}", type=type_)
    db.add(category)
    db.commit()
    category_id = str(category.id)
    db.close()
    return category_id

@pytest.fixture
def item_category_id():
    """ID of a fresh item category, for creating listings."""
    return _create_category(CategoryType.item)

@pytest.fixture
def service_category_id():
    """ID of a fresh service category, for creating services."""
    return _create_category(CategoryType.service)

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    """Register and log in a test user, return auth headers."""
    client.post("/auth/register", json={
        "name": "Test User",
        "email": "test@example.com",
        "password": "testpass123",
    })
    # Login expects JSON not form data
    response = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "testpass123",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def second_auth_headers(client):
    """A second user for testing ownership restrictions."""
    client.post("/auth/register", json={
        "name": "Second User",
        "email": "second@example.com",
        "password": "testpass123",
    })
    response = client.post("/auth/login", json={
        "email": "second@example.com",
        "password": "testpass123",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------- Shared payment fixtures (no real Flutterwave calls) ----------

@pytest.fixture
def third_auth_headers(client):
    """A third user, so two different buyers can compete for one listing."""
    client.post("/auth/register", json={
        "name": "Third User",
        "email": "third@example.com",
        "password": "testpass123",
    })
    token = client.post("/auth/login", json={
        "email": "third@example.com",
        "password": "testpass123",
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def listing_id(client, auth_headers, item_category_id):
    return client.post("/listings/", headers=auth_headers, json={
        "title": "Standing fan",
        "description": "Works well",
        "price": 15000.0,
        "category_id": item_category_id,
    }).json()["id"]


@pytest.fixture
def fake_flutterwave(monkeypatch):
    """Stand-in for the Flutterwave call; records what would have been sent."""
    calls = []

    async def fake_initiate_payment(amount, email, order_id):
        calls.append({"amount": amount, "email": email, "order_id": order_id})
        return {"reference": f"test-ref-{len(calls)}", "payment_link": "https://example.com/pay"}

    monkeypatch.setattr(transactions_router, "initiate_payment", fake_initiate_payment)
    return calls


class _FakeFlutterwaveClient:
    """Stands in for httpx.AsyncClient inside verify_payment."""
    reply: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        reply = self.reply

        class _Response:
            def json(self):
                return reply

        return _Response()


@pytest.fixture
def flutterwave_says(monkeypatch):
    import app.services.transaction_service as transaction_service

    monkeypatch.setattr(transaction_service.httpx, "AsyncClient", _FakeFlutterwaveClient)

    def set_reply(amount, currency="NGN", status="successful"):
        _FakeFlutterwaveClient.reply = {
            "status": "success",
            "data": {"status": status, "amount": amount, "currency": currency},
        }

    return set_reply
