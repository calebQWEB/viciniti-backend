def test_dashboard_stats_returns_zero_counts_for_new_user(client, auth_headers):
    response = client.get("/dashboard/stats", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "balance": 0.0,
        "active_listings": 0,
        "pending_orders": 0,
        "unread_messages": 0,
    }