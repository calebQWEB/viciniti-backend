import pytest

LISTING_PAYLOAD = {
    "title": "MacBook Pro",
    "description": "M2 chip, 16GB RAM",
    "price": 1500000.0,
    "category": "Electronics",
    "images": [],
    "location": "Lagos",
    "latitude": 6.5244,
    "longitude": 3.3792,
}

def test_create_order_success(client, auth_headers, second_auth_headers):
    # First user creates a listing
    listing = client.post("/listings/", 
        json=LISTING_PAYLOAD, 
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
    assert data["fee"] == 75000.0  # 5% of 1500000

def test_cannot_buy_own_listing(client, auth_headers):
    listing = client.post("/listings/",
        json=LISTING_PAYLOAD,
        headers=auth_headers
    ).json()
    response = client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "cannot buy your own" in response.json()["detail"]

def test_cannot_buy_sold_listing(client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=LISTING_PAYLOAD,
        headers=auth_headers
    ).json()

    # Second user buys it first
    client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )

    # Try to buy again — should fail
    response = client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    assert response.status_code == 400
    assert "no longer available" in response.json()["detail"]

def test_get_my_purchases(client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=LISTING_PAYLOAD,
        headers=auth_headers
    ).json()
    client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    response = client.get("/orders/my-purchases", headers=second_auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_get_my_sales(client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=LISTING_PAYLOAD,
        headers=auth_headers
    ).json()
    client.post("/orders/",
        json={"listing_id": listing["id"]},
        headers=second_auth_headers
    )
    response = client.get("/orders/my-sales", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_update_order_status(client, auth_headers, second_auth_headers):
    listing = client.post("/listings/",
        json=LISTING_PAYLOAD,
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