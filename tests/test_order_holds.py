from datetime import datetime, timedelta

import pytest

from app.config import UNPAID_ORDER_MINUTES
from app.models.listing import Listing, ListingStatus
from app.models.order import Order, OrderStatus
from tests.conftest import TestingSessionLocal


def _buy(client, headers, listing_id):
    return client.post("/orders/", json={"listing_id": listing_id}, headers=headers)


def _update(model, row_id, **fields):
    db = TestingSessionLocal()
    row = db.query(model).filter(model.id == row_id).first()
    for name, value in fields.items():
        setattr(row, name, value)
    db.commit()
    db.close()


def _age_order(order_id, minutes):
    _update(Order, order_id, created_at=datetime.utcnow() - timedelta(minutes=minutes))


# ---------- Placing orders ----------

def test_second_buyer_is_held_off_while_first_is_paying(
    client, listing_id, second_auth_headers, third_auth_headers
):
    assert _buy(client, second_auth_headers, listing_id).status_code == 200
    response = _buy(client, third_auth_headers, listing_id)
    assert response.status_code == 409
    assert "already buying" in response.json()["detail"]


def test_hold_expires_after_the_payment_window(
    client, listing_id, second_auth_headers, third_auth_headers
):
    first = _buy(client, second_auth_headers, listing_id).json()
    _age_order(first["id"], UNPAID_ORDER_MINUTES + 1)
    response = _buy(client, third_auth_headers, listing_id)
    assert response.status_code == 200
    assert response.json()["id"] != first["id"]


@pytest.mark.parametrize("paid_status", [OrderStatus.paid, OrderStatus.fulfilled, OrderStatus.disputed])
def test_paid_orders_hold_the_listing_indefinitely(
    client, listing_id, second_auth_headers, third_auth_headers, paid_status
):
    first = _buy(client, second_auth_headers, listing_id).json()
    _update(Order, first["id"], status=paid_status)
    _age_order(first["id"], UNPAID_ORDER_MINUTES * 10)
    assert _buy(client, third_auth_headers, listing_id).status_code == 409


def test_cancelled_orders_release_the_listing(
    client, listing_id, second_auth_headers, third_auth_headers
):
    first = _buy(client, second_auth_headers, listing_id).json()
    _update(Order, first["id"], status=OrderStatus.cancelled)
    assert _buy(client, third_auth_headers, listing_id).status_code == 200


# ---------- Starting a payment ----------

def _pay(client, headers, order_id):
    return client.post(
        "/transactions/initiate-payment",
        json={"amount": 15000.0, "order_id": order_id},
        headers=headers,
    )


def test_payment_starts_for_a_fresh_order(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    response = _pay(client, second_auth_headers, order["id"])
    assert response.status_code == 200
    assert len(fake_flutterwave) == 1


def test_payment_refused_when_item_already_sold(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    _update(Listing, listing_id, status=ListingStatus.sold)
    response = _pay(client, second_auth_headers, order["id"])
    assert response.status_code == 400
    assert "already been sold" in response.json()["detail"]
    assert fake_flutterwave == []  # Flutterwave never contacted


def test_payment_refused_when_order_not_pending(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    _update(Order, order["id"], status=OrderStatus.cancelled)
    response = _pay(client, second_auth_headers, order["id"])
    assert response.status_code == 400
    assert fake_flutterwave == []


def test_payment_refused_when_order_expired(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    _age_order(order["id"], UNPAID_ORDER_MINUTES + 1)
    response = _pay(client, second_auth_headers, order["id"])
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]
    assert fake_flutterwave == []


def test_payment_for_unknown_order_is_404(client, second_auth_headers, fake_flutterwave):
    response = _pay(client, second_auth_headers, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert fake_flutterwave == []


# ---------- Who pays, and how much ----------

def test_charge_uses_the_order_amount_not_the_browsers(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    response = client.post(
        "/transactions/initiate-payment",
        json={"amount": 100.0, "order_id": order["id"]},  # tampered amount
        headers=second_auth_headers,
    )
    assert response.status_code == 200
    assert fake_flutterwave[0]["amount"] == 15000.0


def test_amount_can_be_omitted(client, listing_id, second_auth_headers, fake_flutterwave):
    order = _buy(client, second_auth_headers, listing_id).json()
    response = client.post(
        "/transactions/initiate-payment",
        json={"order_id": order["id"]},
        headers=second_auth_headers,
    )
    assert response.status_code == 200
    assert fake_flutterwave[0]["amount"] == 15000.0


def test_cannot_pay_for_someone_elses_order(
    client, listing_id, second_auth_headers, third_auth_headers, fake_flutterwave
):
    order = _buy(client, second_auth_headers, listing_id).json()
    response = _pay(client, third_auth_headers, order["id"])
    assert response.status_code == 404
    assert fake_flutterwave == []


# ---------- Verifying with Flutterwave ----------


@pytest.mark.parametrize("amount, currency, status, expected", [
    (15000.0, "NGN", "successful", True),
    (16000.0, "NGN", "successful", True),   # overpaying is still a valid payment
    (14999.0, "NGN", "successful", False),  # underpaid
    (100.0, "NGN", "successful", False),
    (15000.0, "USD", "successful", False),  # wrong currency
    (15000.0, "NGN", "failed", False),
])
def test_verification_checks_amount_and_currency(
    client, listing_id, second_auth_headers, flutterwave_says, amount, currency, status, expected
):
    import asyncio
    from app.services.transaction_service import verify_payment

    order = _buy(client, second_auth_headers, listing_id).json()
    flutterwave_says(amount, currency, status)

    db = TestingSessionLocal()
    try:
        assert asyncio.run(verify_payment("ref", order["id"], db)) is expected
    finally:
        db.close()
