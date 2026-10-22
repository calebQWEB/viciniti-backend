import pytest

from app.config import get_settings
from app.models.listing import Listing, ListingStatus
from app.models.order import Order, OrderStatus
from app.models.transaction import Transaction, TransactionStatus
from tests.conftest import TestingSessionLocal

WEBHOOK = "/transactions/webhooks/flutterwave"
GENUINE = {"verif-hash": get_settings().FLUTTERWAVE_HASH_KEY}


@pytest.fixture
def started_payment(client, listing_id, second_auth_headers, fake_flutterwave):
    """A buyer has placed an order and opened the payment page; returns (order_id, reference)."""
    order = client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers).json()
    reference = client.post(
        "/transactions/initiate-payment", json={"order_id": order["id"]}, headers=second_auth_headers
    ).json()["reference"]
    return order["id"], reference


def _state(order_id, reference):
    """(order status, listing status, transaction status) as stored."""
    db = TestingSessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    listing = db.query(Listing).filter(Listing.id == order.listing_id).first()
    tx = db.query(Transaction).filter(Transaction.reference == reference).first()
    result = (order.status, listing.status, tx.status)
    db.close()
    return result


def _payment_event(reference):
    return {"event": "charge.completed", "data": {"status": "successful", "tx_ref": reference}}


# ---------- The secret hash ----------

@pytest.mark.parametrize("headers", [{}, {"verif-hash": "guess"}, {"verif-hash": ""}])
def test_webhook_without_the_secret_hash_is_rejected(client, started_payment, headers):
    order_id, reference = started_payment
    response = client.post(WEBHOOK, json=_payment_event(reference), headers=headers)
    assert response.status_code == 401
    assert _state(order_id, reference)[0] == OrderStatus.pending


def test_fake_chargeback_without_hash_changes_nothing(client, started_payment):
    order_id, reference = started_payment
    fake = {"event": "charge.dispute", "data": {"tx_ref": reference, "dispute_status": "lost"}}
    assert client.post(WEBHOOK, json=fake).status_code == 401
    assert _state(order_id, reference) == (OrderStatus.pending, ListingStatus.active, TransactionStatus.pending)


# ---------- Re-checking with Flutterwave ----------

def test_genuine_webhook_marks_order_paid(client, started_payment, flutterwave_says):
    order_id, reference = started_payment
    flutterwave_says(15000.0)
    response = client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE)
    assert response.status_code == 200
    assert _state(order_id, reference) == (OrderStatus.paid, ListingStatus.sold, TransactionStatus.success)


def test_webhook_flutterwave_does_not_confirm_is_ignored(client, started_payment, flutterwave_says):
    # Correct hash, but Flutterwave's API says the payment didn't go through
    order_id, reference = started_payment
    flutterwave_says(15000.0, status="failed")
    response = client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE)
    assert response.json()["status"] == "ignored"
    assert _state(order_id, reference) == (OrderStatus.pending, ListingStatus.active, TransactionStatus.pending)


def test_webhook_for_underpayment_is_ignored(client, started_payment, flutterwave_says):
    order_id, reference = started_payment
    flutterwave_says(100.0)
    assert client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE).json()["status"] == "ignored"
    assert _state(order_id, reference)[0] == OrderStatus.pending


def test_duplicate_webhook_is_processed_once(client, started_payment, flutterwave_says):
    order_id, reference = started_payment
    flutterwave_says(15000.0)
    client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE)
    again = client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE)
    assert again.json()["message"] == "Already processed"


# ---------- Payments that arrive after the order expired ----------

def _cancel(order_id):
    db = TestingSessionLocal()
    db.query(Order).filter(Order.id == order_id).update({"status": OrderStatus.cancelled})
    db.commit()
    db.close()


def test_late_payment_via_verify_is_flagged_not_revived(
    client, started_payment, second_auth_headers, flutterwave_says
):
    order_id, reference = started_payment
    _cancel(order_id)
    flutterwave_says(15000.0)
    response = client.post(
        "/transactions/verify-payment", json={"reference": reference}, headers=second_auth_headers
    ).json()
    assert response["status"] == "needs_refund"
    assert "refund" in response["message"]
    # Money recorded as received, but the order stays cancelled and the item stays on sale
    assert _state(order_id, reference) == (OrderStatus.cancelled, ListingStatus.active, TransactionStatus.success)


def test_late_payment_via_webhook_is_flagged_not_revived(client, started_payment, flutterwave_says):
    order_id, reference = started_payment
    _cancel(order_id)
    flutterwave_says(15000.0)
    assert client.post(WEBHOOK, json=_payment_event(reference), headers=GENUINE).status_code == 200
    assert _state(order_id, reference)[:2] == (OrderStatus.cancelled, ListingStatus.active)


def test_verify_marks_a_pending_order_paid(client, started_payment, second_auth_headers, flutterwave_says):
    order_id, reference = started_payment
    flutterwave_says(15000.0)
    response = client.post(
        "/transactions/verify-payment", json={"reference": reference}, headers=second_auth_headers
    ).json()
    assert response["status"] == "success"
    assert _state(order_id, reference) == (OrderStatus.paid, ListingStatus.sold, TransactionStatus.success)
