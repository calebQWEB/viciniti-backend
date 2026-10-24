import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

import app.services.payment_service as payment_service
import app.utils.scheduler as scheduler
from app.models.app_log import AppLog
from app.models.bank_account import BankAccount
from app.models.notification import Notification
from app.models.order import Order, OrderStatus
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.services.log_service import log_event
from tests.conftest import TestingSessionLocal

ORDERS = "/admin/orders"


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


def _add_bank(email="test@example.com"):
    db = TestingSessionLocal()
    db.add(BankAccount(user_id=_user_id(email), bank_name="Test Bank", bank_code="000",
                       account_number="0123456789", account_name="Seller", is_default=True))
    db.commit()
    db.close()


def _order(status=OrderStatus.completed, amount=20000.0, fee=800.0, payment=None, **fields):
    """An order sold by test@example.com to second@example.com, optionally with a buyer payment."""
    db = TestingSessionLocal()
    order = Order(buyer_id=_user_id("second@example.com"), seller_id=_user_id("test@example.com"),
                  amount=amount, fee=fee, status=status, **fields)
    db.add(order)
    db.flush()
    if payment is not None:
        db.add(Transaction(user_id=order.buyer_id, order_id=order.id, reference=payment.get("reference", f"JNC-{uuid.uuid4().hex[:8]}"),
                           amount=amount, fee=fee, type=TransactionType.payment,
                           status=payment.get("status", TransactionStatus.success),
                           chargeback_reason=payment.get("reason"),
                           chargeback_filed_at=payment.get("filed_at")))
    db.commit()
    order_id = str(order.id)
    db.close()
    return order_id


def _get(order_id):
    db = TestingSessionLocal()
    order = db.get(Order, uuid.UUID(order_id))
    db.expunge_all()
    db.close()
    return order


def _due(**fields):
    return _order(payout_due_at=datetime.utcnow() - timedelta(hours=1), **fields)


class _FakeFlutterwave:
    """Stands in for httpx.AsyncClient on the transfers endpoint."""
    reply = {"status": "success", "message": "Transfer Queued Successfully"}
    calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        type(self).calls += 1
        reply = type(self).reply

        class _Response:
            def json(self):
                return reply
        return _Response()


@pytest.fixture
def flutterwave(monkeypatch):
    _FakeFlutterwave.reply = {"status": "success", "message": "Transfer Queued Successfully"}
    _FakeFlutterwave.calls = 0
    monkeypatch.setattr(payment_service.httpx, "AsyncClient", _FakeFlutterwave)
    return _FakeFlutterwave


@pytest.fixture
def admin_headers(client, auth_headers, second_auth_headers):
    """test@example.com is the admin (and the seller in these orders); second@example.com buys."""
    _set_admin("test@example.com")
    return auth_headers


# ---------- Access ----------

def test_non_admins_get_404(client, auth_headers):
    for path in ("/admin/overview", ORDERS, f"{ORDERS}/queues"):
        assert client.get(path, headers=auth_headers).status_code == 404
    assert client.post(f"{ORDERS}/retry-payouts", headers=auth_headers).status_code == 404


# ---------- Overview ----------

def test_overview_numbers(client, admin_headers):
    _order(status=OrderStatus.completed, payout_completed_at=datetime.utcnow())  # paid out
    _order(status=OrderStatus.completed)                                          # owed, blocked
    _due()                                                                        # owed, failing
    _order(status=OrderStatus.paid, amount=5000.0, fee=200.0)
    _order(status=OrderStatus.cancelled)                                          # never paid
    _order(status=OrderStatus.cancelled, payment={})                              # refund owed
    log_event("critical", "payout", "payout.failed", "x")

    body = client.get("/admin/overview", headers=admin_headers).json()
    assert body["users_total"] == 2 and body["users_new_7d"] == 2
    assert body["orders_by_status"]["completed"] == 3 and body["orders_by_status"]["cancelled"] == 2
    assert body["all_time"] == {"sales": 65000.0, "fees": 2400.0, "payouts_sent": 19200.0}
    assert body["last_30d"] == body["all_time"]
    assert body["payouts_owed"] == 38400.0
    assert body["attention"] == {"failing_payouts": 1, "blocked_payouts": 1, "held_payouts": 0, "refunds": 1,
                                 "disputes": 0, "critical_logs": 1}
    assert len(body["daily"]) == 30
    assert body["daily"][-1]["orders"] == 4 and body["daily"][-1]["value"] == 65000.0


# ---------- Queues ----------

def test_queues_follow_their_rules(client, admin_headers):
    failing = _due(payout_attempts=2, payout_last_error="Please enable IP Whitelisting")
    _order(payout_due_at=datetime.utcnow() + timedelta(days=2))   # not due yet: in no queue
    blocked = _order()
    refund = _order(status=OrderStatus.cancelled, payment={"reference": "JNC-LATE1"})
    _order(status=OrderStatus.cancelled)                           # cancelled, never paid: nothing owed
    _order(status=OrderStatus.refunded, payment={})                # already refunded
    dispute = _order(status=OrderStatus.disputed, payment={
        "status": TransactionStatus.chargeback_filed, "reason": "Item not received", "filed_at": datetime.utcnow(),
    })

    body = client.get(f"{ORDERS}/queues", headers=admin_headers).json()
    assert body["counts"] == {"failing_payouts": 1, "blocked_payouts": 1, "held_payouts": 0, "refunds": 1,
                              "disputes": 1}
    [item] = body["failing_payouts"]
    assert item["id"] == failing and item["payout_attempts"] == 2
    assert item["payout_last_error"] == "Please enable IP Whitelisting"
    assert item["payout_amount"] == 19200.0 and item["seller"]["email"] == "test@example.com"
    assert body["blocked_payouts"][0]["id"] == blocked
    assert (body["refunds"][0]["id"], body["refunds"][0]["payment_reference"]) == (refund, "JNC-LATE1")
    assert (body["disputes"][0]["id"], body["disputes"][0]["dispute_reason"]) == (dispute, "Item not received")


# ---------- Search ----------

def test_search_and_filters(client, admin_headers):
    first = _order(payment={"reference": "JNC-FINDME"})
    second = _order(status=OrderStatus.paid)

    def ids(params):
        return [i["id"] for i in client.get(ORDERS, params=params, headers=admin_headers).json()["items"]]

    assert ids({"search": "findme"}) == [first]
    assert ids({"search": first[:8]}) == [first]
    assert set(ids({"search": "second@example"})) == {first, second}
    assert ids({"status": "paid"}) == [second]
    assert ids({"search": "nobody"}) == []
    assert client.get(ORDERS, params={"status": "weird"}, headers=admin_headers).status_code == 400


# ---------- Detail ----------

def test_order_detail(client, admin_headers):
    _add_bank()
    order_id = _due(payment={"reference": "JNC-PAID1"}, completed_at=datetime.utcnow() - timedelta(days=4),
                    buyer_accepted_at=datetime.utcnow() - timedelta(days=4), payout_attempts=1,
                    payout_last_error="Please enable IP Whitelisting")
    log_event("critical", "payout", "payout.failed", "Flutterwave rejected a seller payout",
              details={"order_id": order_id})
    log_event("info", "order", "order.created", "Someone else's order", details={"order_id": str(uuid.uuid4())})

    body = client.get(f"{ORDERS}/{order_id}", headers=admin_headers).json()
    assert body["seller_bank"] == {"bank_name": "Test Bank", "account_name": "Seller", "account_last4": "6789"}
    assert [t["reference"] for t in body["transactions"]] == ["JNC-PAID1"]
    assert [log["event"] for log in body["logs"]] == ["payout.failed"]
    labels = [step["label"] for step in body["timeline"]]
    assert labels == ["Order placed", "Payment received", "Seller marked it fulfilled", "Buyer confirmed",
                      "Payout failed (1 attempt)"]
    assert body["timeline"][-1]["tone"] == "problem"
    assert body["can_retry_payout"] is True and body["can_mark_refunded"] is False
    assert client.get(f"{ORDERS}/{uuid.uuid4()}", headers=admin_headers).status_code == 404


# ---------- Retry payout ----------

def test_retry_sends_the_payout_once(client, admin_headers, flutterwave):
    _add_bank()
    order_id = _due(payout_attempts=1, payout_last_error="Please enable IP Whitelisting")

    body = client.post(f"{ORDERS}/{order_id}/retry-payout", headers=admin_headers).json()
    assert (body["ok"], body["outcome"]) == (True, "sent")

    order = _get(order_id)
    assert order.payout_completed_at and order.payout_due_at is None
    assert (order.payout_attempts, order.payout_last_error) == (2, None)
    db = TestingSessionLocal()
    payouts = db.query(Transaction).filter(Transaction.type == TransactionType.payout).all()
    db.close()
    assert [(p.amount, p.status) for p in payouts] == [(19200.0, TransactionStatus.success)]

    # Already paid: refused, and Flutterwave isn't called again
    assert client.post(f"{ORDERS}/{order_id}/retry-payout", headers=admin_headers).status_code == 400
    assert flutterwave.calls == 1


def test_rejected_retry_records_the_error(client, admin_headers, flutterwave):
    _add_bank()
    order_id = _due()
    flutterwave.reply = {"status": "error", "message": "Please enable IP Whitelisting to access this service"}

    body = client.post(f"{ORDERS}/{order_id}/retry-payout", headers=admin_headers).json()
    assert (body["ok"], body["outcome"]) == (False, "rejected")
    order = _get(order_id)
    assert order.payout_attempts == 1 and order.payout_completed_at is None
    assert order.payout_last_error == "Please enable IP Whitelisting to access this service"

    db = TestingSessionLocal()
    retried = db.query(AppLog).filter(AppLog.event == "admin.payout_retried").one()
    db.close()
    assert retried.details["outcome"] == "rejected"


def test_crashed_attempt_is_flagged(client, admin_headers, monkeypatch):
    _add_bank()
    order_id = _due()

    class Exploding(_FakeFlutterwave):
        async def post(self, url, json=None, headers=None):
            raise ConnectionError("network dropped")

    monkeypatch.setattr(payment_service.httpx, "AsyncClient", Exploding)
    assert client.post(f"{ORDERS}/{order_id}/retry-payout", headers=admin_headers).json()["outcome"] == "crashed"
    item = client.get(f"{ORDERS}/queues", headers=admin_headers).json()["failing_payouts"][0]
    assert item["payout_last_attempt_crashed"] is True
    assert item["payout_last_error"].startswith("Crashed: ConnectionError")


def test_locked_order_is_not_paid_twice(client, admin_headers, flutterwave):
    _add_bank()
    order_id = _due()

    # Another worker is mid-payout and holds the row lock
    holder = TestingSessionLocal()
    holder.query(Order).filter(Order.id == uuid.UUID(order_id)).with_for_update().one()
    db = TestingSessionLocal()
    try:
        result = asyncio.run(payment_service.send_payout(db, uuid.UUID(order_id)))
    finally:
        db.close()
        holder.rollback()
        holder.close()

    assert result.outcome == "busy"
    assert flutterwave.calls == 0
    assert _get(order_id).payout_attempts == 0


def test_retry_refused_when_nothing_is_due(client, admin_headers, flutterwave):
    for order_id in (_order(payout_due_at=datetime.utcnow() + timedelta(days=1)),  # not due yet
                     _order(status=OrderStatus.paid),
                     _order()):                                                   # blocked, no due date
        assert client.post(f"{ORDERS}/{order_id}/retry-payout", headers=admin_headers).status_code == 400
    assert flutterwave.calls == 0


def test_retry_all_failing_payouts(client, admin_headers, flutterwave):
    _add_bank()
    first, second = _due(), _due()
    _order()  # blocked: not retried

    body = client.post(f"{ORDERS}/retry-payouts", headers=admin_headers).json()
    assert (body["attempted"], body["sent"]) == (2, 2)
    assert {r["order_id"] for r in body["results"]} == {first, second}
    assert client.get(f"{ORDERS}/queues", headers=admin_headers).json()["counts"]["failing_payouts"] == 0


def test_scheduler_uses_the_same_safe_payout(client, auth_headers, second_auth_headers, flutterwave, monkeypatch):
    _add_bank()
    order_id = _due()
    monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)
    asyncio.run(scheduler.process_due_payouts())
    order = _get(order_id)
    assert order.payout_completed_at and order.payout_due_at is None and order.payout_attempts == 1
    asyncio.run(scheduler.process_due_payouts())
    assert flutterwave.calls == 1


# ---------- Mark refunded ----------

def test_mark_refunded(client, admin_headers):
    order_id = _order(status=OrderStatus.cancelled, payment={"reference": "JNC-LATE2"})
    body = client.post(f"{ORDERS}/{order_id}/mark-refunded", headers=admin_headers,
                       json={"reference": " BANK-123 ", "note": "Sent from the business account"}).json()

    assert body["status"] == "refunded"
    assert (body["refund_reference"], body["refund_note"]) == ("BANK-123", "Sent from the business account")
    assert body["refunded_by"]["email"] == "test@example.com"
    assert body["timeline"][-1]["label"] == "Refunded by admin"
    assert body["can_mark_refunded"] is False
    assert client.get(f"{ORDERS}/queues", headers=admin_headers).json()["counts"]["refunds"] == 0

    db = TestingSessionLocal()
    notice = db.query(Notification).filter(Notification.user_id == _user_id("second@example.com")).one()
    db.close()
    assert "refund of ₦20,000" in notice.message


def test_mark_refunded_only_for_paid_cancelled_orders(client, admin_headers):
    for order_id in (_order(status=OrderStatus.cancelled),          # no payment taken
                     _order(status=OrderStatus.completed, payment={})):
        response = client.post(f"{ORDERS}/{order_id}/mark-refunded", headers=admin_headers, json={})
        assert response.status_code == 400
