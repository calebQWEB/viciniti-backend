import math
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.listing import Listing
from app.models.service import Service
from app.models.user import User
from tests.conftest import TestingSessionLocal

# Searcher stands in Ikeja
IKEJA = (6.6018, 3.3515)

# (title, lat, lng) — sorted nearest to farthest from Ikeja
PLACES = [
    ("Ikeja", 6.6018, 3.3515),     # 0 km
    ("Yaba", 6.5095, 3.3711),      # ~10 km
    ("Lekki", 6.4698, 3.5852),     # ~30 km
    ("Ibadan", 7.3775, 3.9470),    # ~108 km
    ("Abuja", 9.0765, 7.3986),     # ~525 km
]


def haversine_km(lat1, lng1, lat2, lng2):
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _seed(model, places=PLACES, include_no_coords=True):
    """One seller per row; created_at runs oldest (nearest) to newest (farthest) so sort order is testable."""
    db = TestingSessionLocal()
    base_time = datetime.utcnow() - timedelta(days=1)
    rows = list(places) + ([("Nowhere", None, None)] if include_no_coords else [])
    for i, (title, lat, lng) in enumerate(rows):
        seller = User(name=f"Seller {title}", email=f"{uuid.uuid4().hex}@example.com")
        db.add(seller)
        db.flush()
        db.add(model(
            user_id=seller.id,
            title=title,
            description=f"{title} test row",
            price=1000.0,
            location=title,
            latitude=lat,
            longitude=lng,
            created_at=base_time + timedelta(minutes=i),
        ))
    db.commit()
    db.close()


def _near_ikeja(**params):
    return {"latitude": IKEJA[0], "longitude": IKEJA[1], **params}


@pytest.mark.parametrize("path, model", [("/listings/", Listing), ("/services/", Service)])
class TestBrowseByLocation:
    def test_radius_keeps_only_nearby_nearest_first(self, client, path, model):
        _seed(model)
        response = client.get(path, params=_near_ikeja(radius_km=50))
        assert response.status_code == 200
        assert [r["title"] for r in response.json()] == ["Ikeja", "Yaba", "Lekki"]

    def test_distance_km_is_returned(self, client, path, model):
        _seed(model)
        data = client.get(path, params=_near_ikeja(radius_km=50)).json()
        for row, (_, lat, lng) in zip(data, PLACES):
            # Distances are rounded to the nearest 0.5 km (minimum 0.5) for privacy
            assert row["distance_km"] == max(0.5, round(haversine_km(*IKEJA, lat, lng) * 2) / 2)

    def test_without_location_behaviour_is_unchanged(self, client, path, model):
        _seed(model)
        data = client.get(path).json()
        # Newest first, rows without coordinates included, no distance
        assert [r["title"] for r in data] == ["Nowhere", "Abuja", "Ibadan", "Lekki", "Yaba", "Ikeja"]
        assert all(r["distance_km"] is None for r in data)

    def test_pages_are_full_under_radius_filter(self, client, path, model):
        _seed(model)
        page1 = client.get(path, params=_near_ikeja(radius_km=200, skip=0, limit=2)).json()
        page2 = client.get(path, params=_near_ikeja(radius_km=200, skip=2, limit=2)).json()
        page3 = client.get(path, params=_near_ikeja(radius_km=200, skip=4, limit=2)).json()
        assert [r["title"] for r in page1] == ["Ikeja", "Yaba"]
        assert [r["title"] for r in page2] == ["Lekki", "Ibadan"]
        assert page3 == []

    def test_sort_newest_within_radius(self, client, path, model):
        _seed(model)
        data = client.get(path, params=_near_ikeja(radius_km=50, sort="newest")).json()
        assert [r["title"] for r in data] == ["Lekki", "Yaba", "Ikeja"]
        assert all(r["distance_km"] is not None for r in data)

    @pytest.mark.parametrize("params", [
        {"latitude": 91, "longitude": 3.3},
        {"latitude": 6.5, "longitude": -181},
        {"latitude": 6.5, "longitude": 3.3, "radius_km": 0},
        {"latitude": 6.5, "longitude": 3.3, "radius_km": 501},
        {"latitude": 6.5, "longitude": 3.3, "sort": "cheapest"},
    ])
    def test_invalid_params_rejected(self, client, path, model, params):
        assert client.get(path, params=params).status_code == 422


def test_home_featured_near_location(client):
    _seed(Listing)
    _seed(Service)
    data = client.get("/home/featured", params=_near_ikeja(radius_km=50)).json()
    assert [r["title"] for r in data["items"]] == ["Ikeja", "Yaba", "Lekki"]
    assert [r["title"] for r in data["services"]] == ["Ikeja", "Yaba", "Lekki"]
    assert data["items"][0]["distance_km"] == 0.5


def test_home_featured_returns_nothing_when_nothing_nearby(client):
    _seed(Listing)
    london = {"latitude": 51.5072, "longitude": -0.1276}
    data = client.get("/home/featured", params=london).json()
    assert data["items"] == []


def test_home_featured_one_per_seller_near_location(client):
    db = TestingSessionLocal()
    seller = User(name="Busy Seller", email=f"{uuid.uuid4().hex}@example.com")
    db.add(seller)
    db.flush()
    for title, lat, lng in PLACES[:2]:
        db.add(Listing(user_id=seller.id, title=title, description="x", price=1.0, latitude=lat, longitude=lng))
    db.commit()
    db.close()

    data = client.get("/home/featured", params=_near_ikeja(radius_km=50)).json()
    assert [r["title"] for r in data["items"]] == ["Ikeja"]


def test_home_featured_without_location_unchanged(client):
    _seed(Listing)
    data = client.get("/home/featured").json()
    assert data["items"][0]["title"] == "Nowhere"
    assert all(r["distance_km"] is None for r in data["items"])


@pytest.mark.parametrize("path, model", [("/listings/", Listing), ("/services/", Service)])
class TestSearch:
    def test_matches_title_case_insensitively(self, client, path, model):
        _seed(model)
        data = client.get(path, params={"q": "lekki"}).json()
        assert [r["title"] for r in data] == ["Lekki"]

    def test_matches_description(self, client, path, model):
        _seed(model)
        # Every seeded description ends in "test row"
        data = client.get(path, params={"q": "TEST ROW"}).json()
        assert len(data) == 6

    def test_combines_with_radius(self, client, path, model):
        _seed(model)
        near = client.get(path, params=_near_ikeja(radius_km=50, q="yaba")).json()
        far = client.get(path, params=_near_ikeja(radius_km=50, q="abuja")).json()
        assert [r["title"] for r in near] == ["Yaba"]
        assert far == []

    def test_wildcards_are_literal(self, client, path, model):
        _seed(model)
        assert client.get(path, params={"q": "%"}).json() == []

    def test_blank_query_is_ignored(self, client, path, model):
        _seed(model)
        assert len(client.get(path, params={"q": "   "}).json()) == 6
