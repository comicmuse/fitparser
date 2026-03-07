#!/usr/bin/env python3
"""
Test script for RunCoach API endpoints.
Tests authentication, runs list, run details, and push notifications.
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5000/api/v1"

def test_login():
    """Test login endpoint."""
    print("\n=== Testing Login ===")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "athlete", "password": "runcoach123"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Access token: {data['access_token'][:50]}...")
        print(f"Refresh token: {data['refresh_token'][:50]}...")
        print(f"User ID: {data['user_id']}")
        return data['access_token'], data['refresh_token']
    else:
        print(f"Error: {response.text}")
        return None, None

def test_list_runs(access_token):
    """Test list runs endpoint."""
    print("\n=== Testing List Runs ===")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{BASE_URL}/runs?page=1&per_page=5",
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Total runs: {data['pagination']['total']}")
        print(f"Showing {len(data['runs'])} runs")
        for run in data['runs'][:3]:
            print(f"  - {run['date']}: {run['name']} ({run['distance_km']} km, stage: {run['stage']})")
        return data['runs'][0]['id'] if data['runs'] else None
    else:
        print(f"Error: {response.text}")
        return None

def test_get_run(access_token, run_id):
    """Test get single run endpoint."""
    print(f"\n=== Testing Get Run (ID: {run_id}) ===")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{BASE_URL}/runs/{run_id}",
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Name: {data['name']}")
        print(f"Date: {data['date']}")
        print(f"Distance: {data['distance_km']} km")
        print(f"Duration: {data['duration_formatted']}")
        print(f"Avg Power: {data['avg_power_w']} W")
        print(f"Avg HR: {data['avg_hr']} bpm")
        if data.get('yaml_data'):
            print(f"Has YAML data: Yes")
            if 'blocks' in data['yaml_data']:
                print(f"  Blocks: {list(data['yaml_data']['blocks'].keys())}")
    else:
        print(f"Error: {response.text}")

def test_sync_status(access_token):
    """Test sync status endpoint."""
    print("\n=== Testing Sync Status ===")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{BASE_URL}/sync/status",
        headers=headers
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Stats: {data['stats']}")
        if data['last_sync']:
            print(f"Last sync: {data['last_sync']['status']} at {data['last_sync']['started_at']}")
    else:
        print(f"Error: {response.text}")

def test_token_refresh(refresh_token):
    """Test token refresh endpoint."""
    print("\n=== Testing Token Refresh ===")
    response = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"New access token: {data['access_token'][:50]}...")
        return data['access_token']
    else:
        print(f"Error: {response.text}")
        return None

def test_unauthorized():
    """Test that endpoints reject requests without valid token."""
    print("\n=== Testing Unauthorized Access ===")
    response = requests.get(f"{BASE_URL}/runs")
    print(f"Status (no auth): {response.status_code}")
    assert response.status_code == 401, "Should reject request without token"

    response = requests.get(
        f"{BASE_URL}/runs",
        headers={"Authorization": "Bearer invalid_token"}
    )
    print(f"Status (invalid token): {response.status_code}")
    assert response.status_code == 401, "Should reject request with invalid token"
    print("✓ Unauthorized requests properly rejected")

def main():
    print("=" * 60)
    print("RunCoach API Test Suite")
    print("=" * 60)
    print("Make sure the Flask server is running on port 5000")
    print("Start with: source .venv/bin/activate && runcoach")

    try:
        # Test authentication
        access_token, refresh_token = test_login()
        if not access_token:
            print("\n❌ Login failed. Cannot continue tests.")
            return

        # Test unauthorized access
        test_unauthorized()

        # Test runs endpoints
        run_id = test_list_runs(access_token)
        if run_id:
            test_get_run(access_token, run_id)

        # Test sync status
        test_sync_status(access_token)

        # Test token refresh
        new_access_token = test_token_refresh(refresh_token)
        if new_access_token:
            print("\n✓ Token refresh successful")

        print("\n" + "=" * 60)
        print("✓ All API tests completed!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("\n❌ Connection error. Is the Flask server running?")
        print("Start with: source .venv/bin/activate && runcoach")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")

if __name__ == "__main__":
    main()
