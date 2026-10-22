from app.models.bank_account import BankAccount
from app.models.category import CategoryType
from app.models.user import User
from tests.conftest import TestingSessionLocal, _create_category


def _item_category_id():
    return _create_category(CategoryType.item)


def _me(client, headers):
    return client.get("/users/me", headers=headers).json()


def test_new_user_starts_not_onboarded(client, auth_headers):
    me = _me(client, auth_headers)
    assert me["onboarded_at"] is None
    assert me["intent"] is None


def test_set_intent(client, auth_headers):
    response = client.put("/users/me", json={"intent": "sell"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["intent"] == "sell"
    assert _me(client, auth_headers)["intent"] == "sell"


def test_invalid_intent_rejected(client, auth_headers):
    response = client.put("/users/me", json={"intent": "trade"}, headers=auth_headers)
    assert response.status_code == 422


def test_complete_onboarding_is_idempotent(client, auth_headers):
    first = client.post("/users/me/complete-onboarding", headers=auth_headers)
    assert first.status_code == 200
    onboarded_at = first.json()["onboarded_at"]
    assert onboarded_at is not None

    second = client.post("/users/me/complete-onboarding", headers=auth_headers)
    assert second.json()["onboarded_at"] == onboarded_at


def test_complete_onboarding_requires_auth(client):
    assert client.post("/users/me/complete-onboarding").status_code == 401


def test_getting_started_fresh_user(client, auth_headers):
    response = client.get("/dashboard/getting-started", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "has_location": False,
        "has_avatar": False,
        "has_payout_account": False,
        "has_listing_or_service": False,
    }


def test_getting_started_all_done(client, auth_headers):
    client.put("/users/me", headers=auth_headers, json={
        "location": "Ikeja",
        "latitude": 6.6018,
        "longitude": 3.3515,
        "avatar": "https://res.cloudinary.com/demo/avatar.png",
    })
    client.post("/listings/", headers=auth_headers, json={
        "title": "Desk lamp",
        "description": "Works fine",
        "price": 5000.0,
        "category_id": _item_category_id(),
    })

    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "test@example.com").first()
    db.add(BankAccount(
        user_id=user.id, bank_name="Test Bank", bank_code="000",
        account_number="0123456789", account_name="Test User", is_default=True,
    ))
    db.commit()
    db.close()

    response = client.get("/dashboard/getting-started", headers=auth_headers)
    assert response.json() == {
        "has_location": True,
        "has_avatar": True,
        "has_payout_account": True,
        "has_listing_or_service": True,
    }


def test_can_list_without_payout_account(client, auth_headers):
    response = client.post("/listings/", headers=auth_headers, json={
        "title": "Bicycle",
        "description": "Barely used",
        "price": 40000.0,
        "category_id": _item_category_id(),
    })
    assert response.status_code == 200
    assert response.json()["title"] == "Bicycle"
