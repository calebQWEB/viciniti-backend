import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

import app.services.payment_service as payment_service
import app.utils.scheduler as scheduler
from app.models.app_log import AppLog
from app.models.bank_account import BankAccount
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.user import User
from app.services.log_service import log_event
from tests.conftest import TestingSessionLocal

USERS = "/admin/users"
SELLER = "test@example.com"     # owns the listing from the listing_id fixture
BUYER = "second@example.com"


# ---------- Helpers ----------

def _user_id(email):
    db = TestingSessionLocal()
    user_id = db.query(User.id).filter(User.email == email).scalar()
    db.close()
    return user_id


def _set_admin(email, value=True):
    db = TestingSessionLocal()
    db.query(User).filter(User.email == email).update({"is_admin": value})
    db.commit()
    db.close()


@pytest.fixture
def admin_headers(client, auth_headers, second_auth_headers, third_auth_headers):
    """third@example.com is the admin; test@example.com sells and second@example.com buys."""
    _set_admin("third@example.com")
    return third_auth_headers


def _suspend(client, admin_headers, email=SELLER, **body):
    return client.post(f"{USERS}/{_user_id(email)}/suspend", headers=admin_headers,
                       json={"reason": "Selling counterfeit goods", **body})


def _unsuspend(client, admin_headers, email=SELLER, **body):
    return client.post(f"{USERS}/{_user_id(email)}/unsuspend", headers=admin_headers, json=body)


class _FakeTransfers:
    calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        type(self).calls += 1

        class _Response:
            def json(self):
                return {"status": "success"}
        return _Response()


def _due_order_for_seller():
    db = TestingSessionLocal()
    seller_id = _user_id(SELLER)
    db.add(BankAccount(user_id=seller_id, bank_name="Test Bank", bank_code="000",
                       account_number="0123456789", account_name="Seller", is_default=True))
    order = Order(buyer_id=_user_id(BUYER), seller_id=seller_id, amount=20000.0, fee=800.0,
                  status=OrderStatus.completed, payout_due_at=datetime.utcnow() - timedelta(hours=1))
    db.add(order)
    db.commit()
    order_id = str(order.id)
    db.close()
    return order_id


# ---------- Access ----------

def test_non_admins_get_404(client, auth_headers):
    assert client.get(USERS, headers=auth_headers).status_code == 404
    assert client.post(f"{USERS}/{uuid.uuid4()}/suspend", headers=auth_headers,
                       json={"reason": "x" * 5}).status_code == 404


# ---------- List and detail ----------

def test_search_and_filters(client, admin_headers, listing_id):
    _suspend(client, admin_headers)

    def emails(params):
        return [u["email"] for u in client.get(USERS, params=params, headers=admin_headers).json()["items"]]

    assert emails({"search": "second"}) == [BUYER]
    assert emails({"search": "TEST USER"}) == [SELLER]
    assert emails({"filter": "suspended"}) == [SELLER]
    assert emails({"filter": "admins"}) == ["third@example.com"]
    assert len(emails({"filter": "new"})) == 3

    seller = client.get(USERS, params={"search": SELLER}, headers=admin_headers).json()["items"][0]
    assert (seller["listings_count"], seller["is_suspended"]) == (1, True)
    assert client.get(USERS, params={"filter": "weird"}, headers=admin_headers).status_code == 422


def test_user_detail(client, admin_headers, listing_id):
    order_id = _due_order_for_seller()
    db = TestingSessionLocal()
    db.add(Review(order_id=uuid.UUID(order_id), buyer_id=_user_id(BUYER), seller_id=_user_id(SELLER), rating=4))
    db.commit()
    db.close()
    log_event("warning", "auth", "auth.login_failed", "Failed login attempt", user_id=_user_id(SELLER))

    body = client.get(f"{USERS}/{_user_id(SELLER)}", headers=admin_headers).json()
    assert body["listings_by_status"] == {"active": 1, "sold": 0}
    assert body["as_seller"] == {"count": 1, "value": 20000.0}
    assert body["as_buyer"] == {"count": 0, "value": 0.0}
    assert body["bank"]["account_last4"] == "6789"
    assert (body["rating_average"], body["rating_count"]) == (4.0, 1)
    assert [o["id"] for o in body["recent_orders"]] == [order_id]
    assert "auth.login_failed" in [log["event"] for log in body["logs"]]
    assert client.get(f"{USERS}/{uuid.uuid4()}", headers=admin_headers).status_code == 404


# ---------- Locked out ----------

def test_suspension_ends_open_sessions_and_blocks_login(client, admin_headers, auth_headers, sent_emails):
    sent_emails.clear()
    body = _suspend(client, admin_headers, note="Three buyer complaints").json()
    assert body["is_suspended"] and body["suspension_note"] == "Three buyer complaints"
    assert body["suspended_by"]["email"] == "third@example.com"

    # The token issued before the suspension stops working at once
    response = client.get("/users/me", headers=auth_headers)
    assert response.status_code == 403
    assert response.json()["detail"].startswith("This account has been suspended")
    assert "Selling counterfeit goods" in response.json()["detail"]

    # Right password: told about the suspension. Wrong password: the usual message, nothing revealed
    login = client.post("/auth/login", json={"email": SELLER, "password": "testpass123"})
    assert login.status_code == 403 and "suspended" in login.json()["detail"]
    wrong = client.post("/auth/login", json={"email": SELLER, "password": "nope-nope"})
    assert (wrong.status_code, wrong.json()["detail"]) == (401, "Invalid email or password")

    [email] = sent_emails
    assert email["to"] == SELLER and "suspended" in email["subject"]
    assert "Selling counterfeit goods" in email["html"]


def test_password_reset_is_not_sent_to_suspended_accounts(client, admin_headers, sent_emails):
    _suspend(client, admin_headers, notify=False)
    sent_emails.clear()
    response = client.post("/auth/forgot-password", json={"email": SELLER})
    assert response.status_code == 200
    assert sent_emails == []


def test_unsuspend_restores_access(client, admin_headers, auth_headers, sent_emails):
    _suspend(client, admin_headers, notify=False)
    sent_emails.clear()
    body = _unsuspend(client, admin_headers, note="Appeal accepted").json()
    assert body["is_suspended"] is False and body["suspension_reason"] is None
    assert client.get("/users/me", headers=auth_headers).status_code == 200
    assert [m["to"] for m in sent_emails] == [SELLER]

    db = TestingSessionLocal()
    events = [e for (e,) in db.query(AppLog.event).filter(AppLog.category == "admin").order_by(AppLog.created_at)]
    lifted = db.query(AppLog).filter(AppLog.event == "admin.user_unsuspended").one()
    db.close()
    assert events == ["admin.user_suspended", "admin.user_unsuspended"]
    assert lifted.details["previous_reason"] == "Selling counterfeit goods"
    assert lifted.details["note"] == "Appeal accepted"


# ---------- Hidden, then back ----------

def test_content_is_hidden_and_comes_back(client, admin_headers, auth_headers, listing_id, service_category_id):
    service_id = client.post("/services/", headers=auth_headers, json={
        "title": "Cleaning", "description": "x", "price": 10000.0, "category_id": service_category_id,
    }).json()["id"]
    seller_id = _user_id(SELLER)

    def visible():
        featured = client.get("/home/featured").json()
        return {
            "browse_listing": listing_id in [l["id"] for l in client.get("/listings/").json()],
            "browse_service": service_id in [s["id"] for s in client.get("/services/").json()],
            "featured": bool(featured["items"]) and bool(featured["services"]),
            "listing_page": client.get(f"/listings/{listing_id}").status_code == 200,
            "service_page": client.get(f"/services/{service_id}").status_code == 200,
            "profile": client.get(f"/users/{seller_id}").status_code == 200,
            "profile_stats": client.get(f"/users/{seller_id}/stats").status_code == 200,
            "profile_reviews": client.get(f"/users/{seller_id}/reviews").status_code == 200,
            "stats_count": client.get("/home/stats").json()["active_listings"] == 2,
        }

    assert all(visible().values())
    _suspend(client, admin_headers, notify=False)
    assert not any(visible().values()), visible()
    _unsuspend(client, admin_headers, notify=False)
    assert all(visible().values())


def test_no_new_orders_bookings_or_payments(client, admin_headers, auth_headers, second_auth_headers,
                                            listing_id, service_category_id, fake_flutterwave):
    service_id = client.post("/services/", headers=auth_headers, json={
        "title": "Cleaning", "description": "x", "price": 10000.0, "category_id": service_category_id,
    }).json()["id"]
    open_order = client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers).json()
    _suspend(client, admin_headers, notify=False)

    # An order placed before the suspension can no longer be paid for
    payment = client.post("/transactions/initiate-payment", json={"order_id": open_order["id"]},
                          headers=second_auth_headers)
    assert payment.status_code == 400

    booking = client.post("/bookings/", headers=second_auth_headers, json={
        "service_id": service_id, "scheduled_at": (datetime.utcnow() + timedelta(days=2)).isoformat(),
    })
    assert booking.status_code == 404


def test_new_order_refused_for_suspended_seller(client, admin_headers, third_auth_headers, listing_id):
    _suspend(client, admin_headers, notify=False)
    # Even with a direct link, a fresh order is refused
    db = TestingSessionLocal()
    db.query(User).filter(User.email == "third@example.com").update({"is_admin": False})
    db.commit()
    db.close()
    response = client.post("/orders/", json={"listing_id": listing_id}, headers=third_auth_headers)
    assert response.status_code == 400


# ---------- Payouts held ----------

def test_payouts_are_held_while_suspended(client, admin_headers, monkeypatch):
    order_id = _due_order_for_seller()
    _FakeTransfers.calls = 0
    monkeypatch.setattr(payment_service.httpx, "AsyncClient", _FakeTransfers)
    monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)
    _suspend(client, admin_headers, notify=False)

    # Neither the hourly job nor an admin retry sends money
    asyncio.run(scheduler.process_due_payouts())
    db = TestingSessionLocal()
    result = asyncio.run(payment_service.send_payout(db, uuid.UUID(order_id)))
    db.close()
    assert result.outcome == "seller_suspended"
    assert _FakeTransfers.calls == 0
    assert client.post(f"/admin/orders/{order_id}/retry-payout", headers=admin_headers).status_code == 400

    queues = client.get("/admin/orders/queues", headers=admin_headers).json()
    assert queues["counts"]["held_payouts"] == 1 and queues["counts"]["failing_payouts"] == 0
    detail = client.get(f"/admin/orders/{order_id}", headers=admin_headers).json()
    assert detail["can_retry_payout"] is False
    assert detail["timeline"][-1]["label"] == "Payout held: seller is suspended"

    # Unsuspended: the payout goes out on the next run
    _unsuspend(client, admin_headers, notify=False)
    asyncio.run(scheduler.process_due_payouts())
    assert _FakeTransfers.calls == 1


# ---------- Rules ----------

def test_suspension_rules(client, admin_headers):
    admin_id = _user_id("third@example.com")
    assert client.post(f"{USERS}/{admin_id}/suspend", headers=admin_headers,
                       json={"reason": "Testing myself"}).status_code == 400

    _set_admin(BUYER)
    assert _suspend(client, admin_headers, email=BUYER).status_code == 400

    assert _suspend(client, admin_headers, reason="   ").status_code == 400
    assert _suspend(client, admin_headers, reason="no").status_code == 422
    assert _unsuspend(client, admin_headers).status_code == 400   # not suspended yet
    assert _suspend(client, admin_headers, notify=False).status_code == 200
    assert _suspend(client, admin_headers, notify=False).status_code == 400  # already suspended
