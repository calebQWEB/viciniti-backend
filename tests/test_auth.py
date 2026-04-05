import pytest

def test_register_success(client):
    response = client.post("/auth/register", json={
        "name": "Caleb Ochai",
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    assert response.status_code == 200
    data = response.json()
    # Register returns UserResponse not a token
    assert data["email"] == "caleb@viciniti.com"
    assert data["name"] == "Caleb Ochai"

def test_register_duplicate_email(client):
    client.post("/auth/register", json={
        "name": "Caleb Ochai",
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    response = client.post("/auth/register", json={
        "name": "Caleb Ochai",
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]

def test_login_success(client):
    client.post("/auth/register", json={
        "name": "Caleb Ochai",
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    # Login expects JSON
    response = client.post("/auth/login", json={
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_wrong_password(client):
    client.post("/auth/register", json={
        "name": "Caleb Ochai",
        "email": "caleb@viciniti.com",
        "password": "securepass123",
    })
    response = client.post("/auth/login", json={
        "email": "caleb@viciniti.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 401

def test_login_nonexistent_user(client):
    response = client.post("/auth/login", json={
        "email": "ghost@viciniti.com",
        "password": "securepass123",
    })
    assert response.status_code == 401

def test_get_current_user(client, auth_headers):
    response = client.get("/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@viciniti.com"
    assert data["name"] == "Test User"

def test_get_current_user_no_token(client):
    response = client.get("/users/me")
    assert response.status_code == 401

def test_change_password_success(client, auth_headers):
    response = client.put("/users/me/change-password",
        json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password changed successfully"

def test_change_password_wrong_current(client, auth_headers):
    response = client.put("/users/me/change-password",
        json={
            "current_password": "wrongpassword",
            "new_password": "newpass456",
        },
        headers=auth_headers
    )
    assert response.status_code == 400
    assert "incorrect" in response.json()["detail"]