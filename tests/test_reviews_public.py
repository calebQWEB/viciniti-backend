import uuid
from datetime import datetime, timedelta

import pytest

from app.models.listing import Listing
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.service import Service
from app.models.user import User
from app.services.review_service import short_name
from tests.conftest import TestingSessionLocal


def _user(db, name):
    user = User(name=name, email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    db.flush()
    return user


def _review(db, seller, buyer, rating, *, listing=None, service=None, text=None, days_ago=0):
    order = Order(
        listing_id=listing.id if listing else None,
        service_id=service.id if service else None,
        buyer_id=buyer.id,
        seller_id=seller.id,
        amount=1000.0,
        fee=40.0,
        status=OrderStatus.completed,
    )
    db.add(order)
    db.flush()
    db.add(Review(
        order_id=order.id, buyer_id=buyer.id, seller_id=seller.id,
        rating=rating, review_text=text,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    ))


@pytest.fixture
def seller_with_reviews():
    """A seller with one item review, one service review, and one whose subject is gone."""
    db = TestingSessionLocal()
    seller = _user(db, "Chioma Okafor")
    tunde = _user(db, "Tunde Adeyemi")
    ibrahim = _user(db, "Ibrahim")

    chair = Listing(user_id=seller.id, title="Office chair", description="x", price=20000.0)
    cleaning = Service(user_id=seller.id, title="Home deep cleaning", description="x", price=25000.0)
    db.add_all([chair, cleaning])
    db.flush()

    _review(db, seller, tunde, 5, listing=chair, text="Smooth deal.", days_ago=1)
    _review(db, seller, ibrahim, 4, service=cleaning, days_ago=2)
    _review(db, seller, tunde, 3, days_ago=3)  # order no longer linked to a listing or service
    db.commit()
    seller_id = str(seller.id)
    db.close()
    return seller_id


def test_reviews_show_who_and_what(client, seller_with_reviews):
    data = client.get(f"/users/{seller_with_reviews}/reviews").json()
    assert [(r["reviewer_name"], r["kind"], r["subject_title"], r["rating"]) for r in data] == [
        ("Tunde A.", "bought", "Office chair", 5),
        ("Ibrahim", "booked", "Home deep cleaning", 4),
        ("Tunde A.", "bought", "an item", 3),
    ]
    assert data[0]["review_text"] == "Smooth deal."


def test_reviews_expose_no_ids(client, seller_with_reviews):
    review = client.get(f"/users/{seller_with_reviews}/reviews").json()[0]
    for private in ("buyer_id", "seller_id", "order_id"):
        assert private not in review


def test_no_reviews_is_an_empty_list(client):
    assert client.get(f"/users/{uuid.uuid4()}/reviews").json() == []


@pytest.mark.parametrize("full, expected", [
    ("Tunde Adeyemi", "Tunde A."),
    ("Ada Grace okafor", "Ada O."),
    ("Ibrahim", "Ibrahim"),
    ("  ", "A Junction user"),
])
def test_short_name(full, expected):
    assert short_name(full) == expected
