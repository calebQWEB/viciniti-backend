import pytest

LISTING_PAYLOAD = {
    "title": "iPhone 13 Pro",
    "description": "Brand new, sealed box",
    "price": 500000.0,
    "category": "Electronics",
    "images": [],
    "location": "Lagos",
    "latitude": 6.5244,
    "longitude": 3.3792,
}

def test_create_listing(client, auth_headers):
    response = client.post("/listings/", 
        json=LISTING_PAYLOAD,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "iPhone 13 Pro"
    assert data["price"] == 500000.0
    assert data["status"] == "active"

def test_create_listing_unauthenticated(client):
    response = client.post("/listings/", json=LISTING_PAYLOAD)
    assert response.status_code == 401

def test_get_listings(client, auth_headers):
    client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    response = client.get("/listings")
    assert response.status_code == 200
    assert len(response.json()) >= 1

def test_get_listing_by_id(client, auth_headers):
    create = client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    listing_id = create.json()["id"]
    response = client.get(f"/listings/{listing_id}")
    assert response.status_code == 200
    assert response.json()["id"] == listing_id

def test_get_nonexistent_listing(client):
    response = client.get("/listings/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

def test_get_my_listings(client, auth_headers):
    client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    response = client.get("/listings/me", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1

def test_update_listing(client, auth_headers):
    create = client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    listing_id = create.json()["id"]
    response = client.put(f"/listings/{listing_id}",
        json={**LISTING_PAYLOAD, "title": "iPhone 13 Pro Max", "price": 600000.0},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "iPhone 13 Pro Max"
    assert response.json()["price"] == 600000.0

def test_update_listing_wrong_owner(client, auth_headers, second_auth_headers):
    create = client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    listing_id = create.json()["id"]
    response = client.put(f"/listings/{listing_id}",
        json={**LISTING_PAYLOAD, "title": "Hacked Title"},
        headers=second_auth_headers
    )
    assert response.status_code == 403

def test_delete_listing(client, auth_headers):
    create = client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    listing_id = create.json()["id"]
    response = client.delete(f"/listings/{listing_id}", headers=auth_headers)
    assert response.status_code == 200
    # Verify it's gone
    get = client.get(f"/listings/{listing_id}")
    assert get.status_code == 404

def test_delete_listing_wrong_owner(client, auth_headers, second_auth_headers):
    create = client.post("/listings/", json=LISTING_PAYLOAD, headers=auth_headers)
    listing_id = create.json()["id"]
    response = client.delete(f"/listings/{listing_id}", headers=second_auth_headers)
    assert response.status_code == 403