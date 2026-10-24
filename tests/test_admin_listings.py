import uuid
from datetime import datetime, timedelta

import pytest

from app.models.app_log import AppLog
from app.models.category import Category, CategoryType
from app.models.notification import Notification
from app.models.user import User
from tests.conftest import TestingSessionLocal

SELLER = "test@example.com"


def _user_id(email):
    db = TestingSessionLocal()
    user_id = db.query(User.id).filter(User.email == email).scalar()
    db.close()
    return user_id


@pytest.fixture
def admin_headers(client, auth_headers, second_auth_headers, third_auth_headers):
    """third@example.com is the admin; test@example.com sells and second@example.com buys."""
    db = TestingSessionLocal()
    db.query(User).filter(User.email == "third@example.com").update({"is_admin": True})
    db.commit()
    db.close()
    return third_auth_headers


@pytest.fixture
def service_id(client, auth_headers, service_category_id):
    return client.post("/services/", headers=auth_headers, json={
        "title": "Cleaning", "description": "Deep clean", "price": 10000.0, "category_id": service_category_id,
    }).json()["id"]


def _remove(client, admin_headers, kind, item_id, **body):
    return client.post(f"/admin/listings/{kind}/{item_id}/remove", headers=admin_headers,
                       json={"reason": "Counterfeit item", **body})


def _restore(client, admin_headers, kind, item_id, **body):
    return client.post(f"/admin/listings/{kind}/{item_id}/restore", headers=admin_headers, json=body)


# ---------- Access ----------

def test_non_admins_get_404(client, auth_headers, listing_id):
    assert client.get("/admin/listings", headers=auth_headers).status_code == 404
    assert client.get("/admin/categories", headers=auth_headers).status_code == 404
    assert _remove(client, auth_headers, "item", listing_id).status_code == 404


# ---------- Browse ----------

def test_list_search_and_filters(client, admin_headers, listing_id, service_id, item_category_id):
    def ids(params):
        return [i["id"] for i in client.get("/admin/listings", params=params, headers=admin_headers).json()["items"]]

    assert ids({}) == [listing_id]
    assert ids({"kind": "service"}) == [service_id]
    assert ids({"search": "standing"}) == [listing_id]
    assert ids({"search": "test@example"}) == [listing_id]
    assert ids({"category_id": item_category_id}) == [listing_id]
    assert ids({"seller_id": str(_user_id(SELLER))}) == [listing_id]
    assert ids({"status": "sold"}) == []

    _remove(client, admin_headers, "item", listing_id, notify=False)
    assert ids({"status": "removed"}) == [listing_id]
    assert ids({"status": "active"}) == []
    assert client.get("/admin/listings", params={"status": "weird"}, headers=admin_headers).status_code == 400

    item = client.get("/admin/listings", headers=admin_headers).json()["items"][0]
    assert item["seller"]["email"] == SELLER and item["category"]["id"] == item_category_id


def test_detail(client, admin_headers, listing_id, second_auth_headers):
    client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers)
    body = client.get(f"/admin/listings/item/{listing_id}", headers=admin_headers).json()
    assert (body["title"], body["description"], body["orders_count"]) == ("Standing fan", "Works well", 1)
    assert body["removed_at"] is None and body["removed_by"] is None
    assert client.get(f"/admin/listings/item/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"/admin/listings/vehicle/{listing_id}", headers=admin_headers).status_code == 422


# ---------- Remove and restore ----------

def test_removed_items_are_hidden_and_come_back(client, admin_headers, listing_id, service_id):
    seller_id = _user_id(SELLER)

    def visible():
        featured = client.get("/home/featured").json()
        stats = client.get(f"/users/{seller_id}/stats").json()
        return {
            "browse_listing": listing_id in [l["id"] for l in client.get("/listings/").json()],
            "browse_service": service_id in [s["id"] for s in client.get("/services/").json()],
            "featured_item": bool(featured["items"]),
            "featured_service": bool(featured["services"]),
            "listing_page": client.get(f"/listings/{listing_id}").status_code == 200,
            "service_page": client.get(f"/services/{service_id}").status_code == 200,
            "profile_listing": bool(stats["listings"]),
            "profile_service": bool(stats["services"]),
        }

    assert all(visible().values())
    _remove(client, admin_headers, "item", listing_id, notify=False)
    _remove(client, admin_headers, "service", service_id, notify=False)
    assert not any(visible().values()), visible()
    assert client.get("/home/stats").json()["active_listings"] == 0

    _restore(client, admin_headers, "item", listing_id, notify=False)
    _restore(client, admin_headers, "service", service_id, notify=False)
    assert all(visible().values())


def test_seller_sees_it_but_cannot_edit(client, admin_headers, auth_headers, listing_id):
    _remove(client, admin_headers, "item", listing_id, notify=False)

    mine = client.get("/listings/me", headers=auth_headers).json()["items"][0]
    assert mine["removed_at"] and mine["removal_reason"] == "Counterfeit item"

    for change in ({"title": "Totally new"}, {"status": "active"}):
        response = client.put(f"/listings/{listing_id}", headers=auth_headers, json=change)
        assert response.status_code == 403 and "removed by Junction" in response.json()["detail"]
    # Deleting is still allowed
    assert client.delete(f"/listings/{listing_id}", headers=auth_headers).status_code == 200


def test_no_orders_bookings_or_payments(client, admin_headers, second_auth_headers, third_auth_headers,
                                        listing_id, service_id, fake_flutterwave):
    open_order = client.post("/orders/", json={"listing_id": listing_id}, headers=second_auth_headers).json()
    _remove(client, admin_headers, "item", listing_id, notify=False)
    _remove(client, admin_headers, "service", service_id, notify=False)

    payment = client.post("/transactions/initiate-payment", json={"order_id": open_order["id"]},
                          headers=second_auth_headers)
    assert payment.status_code == 400
    assert client.post("/orders/", json={"listing_id": listing_id}, headers=third_auth_headers).status_code == 400
    booking = client.post("/bookings/", headers=second_auth_headers, json={
        "service_id": service_id, "scheduled_at": (datetime.utcnow() + timedelta(days=2)).isoformat(),
    })
    assert booking.status_code == 404


def test_seller_is_notified_and_actions_are_logged(client, admin_headers, listing_id, sent_emails):
    sent_emails.clear()
    body = _remove(client, admin_headers, "item", listing_id).json()
    assert body["removal_reason"] == "Counterfeit item" and body["removed_by"]["email"] == "third@example.com"
    _restore(client, admin_headers, "item", listing_id)

    assert [m["to"] for m in sent_emails] == [SELLER, SELLER]
    assert "removed" in sent_emails[0]["subject"] and "Counterfeit item" in sent_emails[0]["html"]
    db = TestingSessionLocal()
    messages = [n.message for n in db.query(Notification).filter(Notification.user_id == _user_id(SELLER))
                .order_by(Notification.created_at)]
    events = [e for (e,) in db.query(AppLog.event).filter(AppLog.category == "admin").order_by(AppLog.created_at)]
    db.close()
    assert "removed by Junction: Counterfeit item" in messages[-2] and "restored" in messages[-1]
    assert events == ["admin.listing_removed", "admin.listing_restored"]


def test_removal_rules(client, admin_headers, listing_id, sent_emails):
    assert _remove(client, admin_headers, "item", listing_id, reason="   ").status_code == 400
    assert _remove(client, admin_headers, "item", listing_id, reason="no").status_code == 422
    assert _restore(client, admin_headers, "item", listing_id).status_code == 400
    sent_emails.clear()
    assert _remove(client, admin_headers, "item", listing_id, notify=False).status_code == 200
    assert sent_emails == []
    assert _remove(client, admin_headers, "item", listing_id).status_code == 400


# ---------- Categories ----------

def _categories(client, admin_headers, kind):
    return [c for c in client.get("/admin/categories", headers=admin_headers).json() if c["type"] == kind]


def test_category_list_has_usage_counts(client, admin_headers, listing_id, item_category_id):
    [category] = _categories(client, admin_headers, "item")
    assert category["id"] == item_category_id and category["usage_count"] == 1 and category["is_active"]


def test_create_category(client, admin_headers, item_category_id):
    response = client.post("/admin/categories", headers=admin_headers,
                           json={"name": " Phones & Tablets ", "type": "item", "icon": "smartphone"})
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["slug"], body["icon"], body["usage_count"]) == ("Phones & Tablets", "phones-tablets", "smartphone", 0)
    # Added at the end of its list
    assert [c["slug"] for c in _categories(client, admin_headers, "item")][-1] == "phones-tablets"

    clash = client.post("/admin/categories", headers=admin_headers, json={"name": "Phones, Tablets", "type": "item"})
    assert clash.status_code == 400 and "phones-tablets" in clash.json()["detail"]
    for bad in ({"name": "!!", "type": "item"}, {"name": "Pets", "type": "item", "icon": "Not An Icon"},
                {"name": "Pets", "type": "animal"}):
        assert client.post("/admin/categories", headers=admin_headers, json=bad).status_code in (400, 422)


def test_edit_keeps_the_slug_and_retire_hides_it(client, admin_headers, auth_headers, listing_id, item_category_id):
    body = client.patch(f"/admin/categories/{item_category_id}", headers=admin_headers,
                        json={"name": "Home & Living", "icon": "sofa"}).json()
    assert (body["name"], body["icon"]) == ("Home & Living", "sofa")
    slug = body["slug"]

    client.patch(f"/admin/categories/{item_category_id}", headers=admin_headers, json={"is_active": False})
    assert client.get("/categories/").json() == []
    # Its listing stays visible, still browsable by the unchanged slug, and its seller can still edit other fields
    assert [l["id"] for l in client.get("/listings/", params={"category": slug}).json()] == [listing_id]
    edit = client.put(f"/listings/{listing_id}", headers=auth_headers,
                      json={"title": "Fan", "category_id": item_category_id})
    assert edit.status_code == 200

    client.patch(f"/admin/categories/{item_category_id}", headers=admin_headers, json={"is_active": True})
    assert len(client.get("/categories/").json()) == 1

    db = TestingSessionLocal()
    events = [e for (e,) in db.query(AppLog.event).filter(AppLog.category == "admin").order_by(AppLog.created_at)]
    db.close()
    assert events == ["admin.category_updated", "admin.category_retired", "admin.category_reactivated"]


def test_reorder(client, admin_headers, item_category_id):
    db = TestingSessionLocal()
    db.add(Category(name="Books", slug="books", type=CategoryType.item, sort_order=5))
    db.commit()
    db.close()
    ids = [c["id"] for c in _categories(client, admin_headers, "item")]
    reordered = list(reversed(ids))

    body = client.post("/admin/categories/reorder", headers=admin_headers, json={"type": "item", "ids": reordered}).json()
    assert [c["id"] for c in body if c["type"] == "item"] == reordered
    assert [c["id"] for c in client.get("/categories/", params={"type": "item"}).json()] == reordered

    for bad in (reordered[:1], reordered + reordered[:1], reordered[:1] + [str(uuid.uuid4())]):
        assert client.post("/admin/categories/reorder", headers=admin_headers,
                           json={"type": "item", "ids": bad}).status_code == 400


def test_delete_only_when_unused(client, admin_headers, listing_id, item_category_id, service_category_id):
    in_use = client.delete(f"/admin/categories/{item_category_id}", headers=admin_headers)
    assert in_use.status_code == 400 and "Retire it instead" in in_use.json()["detail"]
    assert client.delete(f"/admin/categories/{service_category_id}", headers=admin_headers).status_code == 204
    assert _categories(client, admin_headers, "service") == []
    assert client.delete(f"/admin/categories/{uuid.uuid4()}", headers=admin_headers).status_code == 404
