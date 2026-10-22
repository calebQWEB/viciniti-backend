import pytest

from app.config import PLATFORM_FEE_CAP, calculate_platform_fee

LISTING_PAYLOAD = {
    "title": "MacBook Pro",
    "description": "M2 chip, 16GB RAM",
    "price": 1500000.0,
    "images": [],
    "location": "Lagos",
    "latitude": 6.5244,
    "longitude": 3.3792,
}

@pytest.fixture
def listing_payload(item_category_id):
    return {**LISTING_PAYLOAD, "category_id": item_category_id}


def test_create_order_success(listing_payload, client, auth_headers, second_auth_headers):
    # First user creates a listing
    listing = client.post("/listings/", 
        json=listing_payload, 
        headers=auth_headers
    ).json()

    # Second user buys it
    response = client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["amount"] == 1500000.0
    # 4% of 1,500,000 is 60,000, so this order hits the fee cap
    assert data["fee"] == calculate_platform_fee(1500000.0) == PLATFORM_FEE_CAP

def test_cannot_buy_own_listing(listing_payload, client, auth_headers):
    listing = client.post("/listings/",
        json=listing_payload,
        headers=auth_headers
    ).json()
    response = client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "cannot buy your own" in response.json()["detail"]

def test_buying_twice_returns_the_same_order(listing_payload, client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=listing_payload,
        headers=auth_headers
    ).json()

    first = client.post("/orders/", json={"listing_id": listing["id"]}, headers=second_auth_headers)
    # Clicking Buy again (e.g. after closing the payment page) reuses the unpaid order
    second = client.post("/orders/", json={"listing_id": listing["id"]}, headers=second_auth_headers)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

def test_get_my_purchases(listing_payload, client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=listing_payload,
        headers=auth_headers
    ).json()
    client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    response = client.get("/orders/my-purchases", headers=second_auth_headers)
    assert response.status_code == 200
    # Paginated: { items, total, page, limit, total_pages }
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1

def test_get_my_sales(listing_payload, client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=listing_payload,
        headers=auth_headers
    ).json()
    client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    response = client.get("/orders/my-sales", headers=auth_headers)
    assert response.status_code == 200
    # Paginated: { items, total, page, limit, total_pages }
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1

def test_update_order_status(listing_payload, client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=listing_payload,
        headers=auth_headers
    ).json()
    order = client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    ).json()
    response = client.put(f"/orders/{order['id']}",
        json={"status": "completed"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"