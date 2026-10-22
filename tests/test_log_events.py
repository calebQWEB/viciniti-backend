import json
from datetime import datetime, timedelta

import pytest
import resend

import app.services.payment_service as payment_service
import app.utils.scheduler as scheduler
from app.config import get_settings
from app.models.app_log import AppLog
from app.models.bank_account import BankAccount
from app.models.order import Order, OrderStatus
from app.models.user import User
from tests.conftest import TestingSessionLocal

WEBHOOK = "/transactions/webhooks/flutterwave"
GENUINE = {"verif-hash": get_settings().FLUTTERWAVE_HASH_KEY}


def _logs(event=None):
    db = TestingSessionLocal()
    query = db.query(AppLog)
    if event:
        query = query.filter(AppLog.event == event)
    rows = query.order_by(AppLog.created_at).all()
    db.expunge_all()
    db.close()
    return rows


def _one(event):
    rows = _logs(event)
    assert len(rows) == 1, f"expected one {event}, got {[r.event for r in _logs()]}"
    return rows[0]


def _user_id(email="test@example.com"):
    db = TestingSessionLocal()
    user_id = db.query(User.id).filter(User.email == email).scalar()
    db.close()
    return user_id


def _make_admin():
    db = TestingSessionLocal()
    db.add(User(name="Admin", email="admin@example.com", is_admin=True))
    db.commit()
    db.close()


@pytest.fixture
def started_payment(client, listing_id, second_auth_headers, fake_flutterwave):
    order = client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers).json()
    reference = client.post(
        "/transactions/initiate-payment", json={"order_id": order["id"]}, headers=second_auth_headers
    ).json()["reference"]
    return order["id"], reference


# ---------- Accounts ----------

def test_register_and_login_are_logged(client, auth_headers):
    user_id = _user_id()
    assert _one("auth.registered").user_id == user_id
    login = _one("auth.login")
    assert (login.level, login.user_id) == ("info", user_id)


def test_failed_login_is_a_warning_with_masked_email(client, auth_headers):
    client.post("/auth/login", json={"email": "test@example.com", "password": "wrong-pass"})
    client.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
    failures = _logs("auth.login_failed")
    assert [f.level for f in failures] == ["warning", "warning"]
    assert failures[0].details == {"email": "t***@example.com", "account_exists": True}
    assert failures[0].user_id == _user_id()
    assert failures[1].details["account_exists"] is False


# ---------- Orders and payments ----------

def test_order_and_payment_lifecycle(client, started_payment, second_auth_headers, flutterwave_says):
    order_id, reference = started_payment
    created = _one("order.created")
    assert created.details["order_id"] == order_id and created.details["amount"] == 15000.0
    assert _one("payment.started").details["reference"] == reference

    flutterwave_says(15000.0)
    client.post("/transactions/verify-payment", json={"reference": reference}, headers=second_auth_headers)
    confirmed = _one("payment.confirmed")
    assert confirmed.details["source"] == "redirect"
    assert confirmed.user_id == _user_id("second@example.com")


def test_underpayment_is_logged_with_amounts(client, started_payment, second_auth_headers, flutterwave_says):
    _, reference = started_payment
    flutterwave_says(100.0)
    client.post("/transactions/verify-payment", json={"reference": reference}, headers=second_auth_headers)
    entry = _one("payment.unconfirmed")
    assert entry.level == "warning"
    assert (entry.details["expected_amount"], entry.details["paid_amount"]) == (15000.0, 100.0)


def test_late_payment_is_critical_and_alerts(client, started_payment, second_auth_headers, flutterwave_says, sent_emails):
    _make_admin()
    order_id, reference = started_payment
    db = TestingSessionLocal()
    db.query(Order).filter(Order.id == order_id).update({"status": OrderStatus.cancelled})
    db.commit()
    db.close()
    sent_emails.clear()

    flutterwave_says(15000.0)
    client.post("/transactions/verify-payment", json={"reference": reference}, headers=second_auth_headers)
    entry = _one("payment.needs_refund")
    assert entry.level == "critical" and entry.alert_sent
    assert any("payment.needs_refund" in m["subject"] for m in sent_emails)


# ---------- Webhooks and chargebacks ----------

def test_rejected_webhook_is_a_warning(client):
    client.post(WEBHOOK, json={"event": "charge.completed", "data": {}}, headers={"verif-hash": "guess"})
    entry = _one("webhook.rejected")
    assert entry.level == "warning"
    assert entry.details == {"hash_present": True}


def test_chargeback_filed_is_critical(client, started_payment, flutterwave_says, sent_emails):
    # Also proves the chargeback service imports again (it used to fail on an "OrderStatusS" typo)
    _make_admin()
    order_id, reference = started_payment
    sent_emails.clear()
    dispute = {"event": "charge.dispute", "data": {
        "tx_ref": reference, "dispute_status": "under_investigation",
        "dispute_reason": "Item not received", "id": "dsp_1",
    }}
    assert client.post(WEBHOOK, json=dispute, headers=GENUINE).status_code == 200

    entry = _one("chargeback.filed")
    assert entry.level == "critical"
    assert entry.details["reason"] == "Item not received"
    assert any("chargeback.filed" in m["subject"] for m in sent_emails)
    db = TestingSessionLocal()
    assert db.query(Order.status).filter(Order.id == order_id).scalar() == OrderStatus.disputed
    db.close()


# ---------- Payouts ----------

class _RejectingFlutterwave:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        class _Response:
            def json(self):
                return {"status": "error", "message": "Insufficient balance"}
        return _Response()


def _completed_order_with_bank(seller_email="test@example.com"):
    db = TestingSessionLocal()
    seller = db.query(User).filter(User.email == seller_email).first()
    buyer = User(name="Buyer", email="buyer@example.com")
    db.add(buyer)
    db.add(BankAccount(user_id=seller.id, bank_name="Test Bank", bank_code="000",
                       account_number="0123456789", account_name="Seller", is_default=True))
    db.flush()
    order = Order(buyer_id=buyer.id, seller_id=seller.id, amount=20000.0, fee=800.0,
                  status=OrderStatus.completed)
    db.add(order)
    db.commit()
    order_id = order.id
    db.close()
    return order_id


def test_rejected_payout_is_critical_and_alerts(client, auth_headers, monkeypatch, sent_emails):
    import asyncio
    _make_admin()
    order_id = _completed_order_with_bank()
    monkeypatch.setattr(payment_service.httpx, "AsyncClient", _RejectingFlutterwave)
    sent_emails.clear()

    db = TestingSessionLocal()
    try:
        assert asyncio.run(payment_service.initiate_seller_payout(db, order_id)) is False
    finally:
        db.close()

    entry = _one("payout.failed")
    assert entry.level == "critical"
    assert entry.details["flutterwave_message"] == "Insufficient balance"
    assert entry.details["amount"] == 19200.0
    assert [m["to"] for m in sent_emails] == ["admin@example.com"]


# ---------- Email and scheduler ----------

def test_email_failure_is_logged_with_masked_recipient(client, monkeypatch):
    def failing_send(params):
        raise RuntimeError("Resend is down")

    monkeypatch.setattr(resend.Emails, "send", staticmethod(failing_send))
    client.post("/auth/register", json={"name": "Ada", "email": "ada@example.com", "password": "testpass123"})
    entry = _one("email.failed")
    assert entry.level == "error"
    assert entry.details["to"] == "a***@example.com"
    assert "Welcome" in entry.details["subject"]


def test_expired_unpaid_order_is_logged(client, listing_id, second_auth_headers, monkeypatch):
    order = client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers).json()
    db = TestingSessionLocal()
    db.query(Order).filter(Order.id == order["id"]).update(
        {"created_at": datetime.utcnow() - timedelta(hours=2)}
    )
    db.commit()
    db.close()

    monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)
    scheduler.cancel_stale_orders()
    assert _one("order.expired").details["order_id"] == order["id"]


def test_crashing_job_is_logged(monkeypatch):
    class BrokenClock:
        @staticmethod
        def utcnow():
            raise RuntimeError("clock broke")

    monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(scheduler, "datetime", BrokenClock)
    scheduler.cancel_stale_orders()
    entry = _one("scheduler.job_failed")
    assert entry.level == "error"
    assert entry.details == {"job": "cancel_stale_orders"}
    assert "clock broke" in entry.traceback


# ---------- Bookings and listings ----------

def test_booking_request_and_accept_are_logged(client, auth_headers, second_auth_headers, service_category_id):
    service = client.post("/services/", headers=auth_headers, json={
        "title": "Cleaning", "description": "x", "price": 10000.0, "category_id": service_category_id,
    }).json()
    assert _one("service.created").details["service_id"] == service["id"]

    booking = client.post("/bookings/", headers=second_auth_headers, json={
        "service_id": service["id"],
        "scheduled_at": (datetime.utcnow() + timedelta(days=2)).isoformat(),
    }).json()
    client.put(f"/bookings/{booking['id']}", headers=auth_headers, json={"status": "confirmed"})

    assert _one("booking.requested").user_id == _user_id("second@example.com")
    accepted = _one("booking.accepted")
    assert accepted.details["from"] == "pending" and accepted.details["to"] == "confirmed"


# ---------- Nothing sensitive is stored ----------

def test_no_passwords_or_full_account_numbers_in_logs(client, auth_headers):
    client.post("/auth/login", json={"email": "test@example.com", "password": "my-secret-pass"})
    client.post("/bank-accounts/", headers=auth_headers, json={
        "bank_name": "Test Bank", "bank_code": "000", "account_number": "0123456789",
        "account_name": "Test User", "is_default": True,
    })
    assert _one("bank_account.added").details["account_number"] == "****6789"

    everything = json.dumps([[e.message, e.details] for e in _logs()])
    for secret in ("testpass123", "my-secret-pass", "0123456789"):
        assert secret not in everything
