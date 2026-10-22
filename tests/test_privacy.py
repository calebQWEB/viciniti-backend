import pytest

from app.models.category import CategoryType
from app.models.user import User
from app.utils.geo import blur_coordinate, round_distance
from tests.conftest import TestingSessionLocal, _create_category

# A precise home location that must never appear in public responses
HOME = {"location": "Ikeja", "latitude": 6.601834, "longitude": 3.351486}


def _category_id(type_=CategoryType.item):
    return _create_category(type_)


def _create(client, headers, path="/listings/", type_=CategoryType.item):
    response = client.post(path, headers=headers, json={
        "title": "Standing fan",
        "description": "Works well",
        "price": 15000.0,
        "category_id": _category_id(type_),
        **HOME,
    })
    assert response.status_code == 200
    return response.json()


def _user_id(email="test@example.com"):
    db = TestingSessionLocal()
    user_id = str(db.query(User).filter(User.email == email).first().id)
    db.close()
    return user_id


# ---------- Public profile ----------

def test_public_profile_hides_email_and_coordinates(client, auth_headers):
    client.put("/users/me", headers=auth_headers, json=HOME)
    data = client.get(f"/users/{_user_id()}").json()
    assert data["name"] == "Test User"
    assert data["location"] == "Ikeja"
    for private in ("email", "latitude", "longitude", "intent", "onboarded_at"):
        assert private not in data


def test_own_profile_still_has_everything(client, auth_headers):
    client.put("/users/me", headers=auth_headers, json=HOME)
    me = client.get("/users/me", headers=auth_headers).json()
    assert me["email"] == "test@example.com"
    assert me["latitude"] == HOME["latitude"]


# ---------- Listing and service coordinates ----------

@pytest.mark.parametrize("path, type_", [("/listings/", CategoryType.item), ("/services/", CategoryType.service)])
class TestListingCoordinates:
    def test_public_get_is_blurred(self, client, auth_headers, path, type_):
        created = _create(client, auth_headers, path, type_)
        data = client.get(f"{path}{created['id']}").json()
        assert data["latitude"] == blur_coordinate(HOME["latitude"]) != HOME["latitude"]
        assert data["longitude"] == blur_coordinate(HOME["longitude"]) != HOME["longitude"]
        assert "exact_coordinates" not in data

    def test_other_users_get_blurred(self, client, auth_headers, second_auth_headers, path, type_):
        created = _create(client, auth_headers, path, type_)
        data = client.get(f"{path}{created['id']}", headers=second_auth_headers).json()
        assert data["latitude"] == blur_coordinate(HOME["latitude"])

    def test_owner_gets_exact(self, client, auth_headers, path, type_):
        created = _create(client, auth_headers, path, type_)
        # Create response goes to the owner too
        assert created["latitude"] == HOME["latitude"]
        data = client.get(f"{path}{created['id']}", headers=auth_headers).json()
        assert data["latitude"] == HOME["latitude"]
        assert data["longitude"] == HOME["longitude"]

    def test_browse_is_blurred(self, client, auth_headers, path, type_):
        _create(client, auth_headers, path, type_)
        rows = client.get(path, headers=auth_headers).json()
        assert rows[0]["latitude"] == blur_coordinate(HOME["latitude"])

    def test_invalid_token_is_treated_as_anonymous(self, client, auth_headers, path, type_):
        created = _create(client, auth_headers, path, type_)
        response = client.get(f"{path}{created['id']}", headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 200
        assert response.json()["latitude"] == blur_coordinate(HOME["latitude"])


def test_user_stats_are_blurred(client, auth_headers):
    _create(client, auth_headers)
    data = client.get(f"/users/{_user_id()}/stats").json()
    assert len(data["listings"]) == 1
    assert data["listings"][0]["latitude"] == blur_coordinate(HOME["latitude"])
    assert "exact_coordinates" not in data["listings"][0]


def test_home_featured_is_blurred(client, auth_headers):
    _create(client, auth_headers)
    item = client.get("/home/featured").json()["items"][0]
    assert item["latitude"] == blur_coordinate(HOME["latitude"])


# ---------- Helpers ----------

@pytest.mark.parametrize("km, expected", [(0.0, 0.5), (0.2, 0.5), (0.8, 1.0), (1.24, 1.0), (1.26, 1.5), (12.7, 12.5)])
def test_round_distance(km, expected):
    assert round_distance(km) == expected


def test_blur_moves_less_than_400_metres():
    # Half the 0.005° grid is ~280 m of latitude
    assert abs(blur_coordinate(6.601834) - 6.601834) <= 0.0025
    assert blur_coordinate(None) is None
