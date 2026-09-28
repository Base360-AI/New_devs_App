"""Integration checks for the seeded assignment stack (run with the API running)."""

import json
import os
import unittest
import urllib.error
import urllib.request


BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://127.0.0.1:8000/api/v1")


def request(path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class DashboardIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = {}
        for tenant, email, password in (
            ("sunset", "sunset@propertyflow.com", "client_a_2024"),
            ("ocean", "ocean@propertyflow.com", "client_b_2024"),
        ):
            status, response = request("/auth/login", body={"email": email, "password": password})
            assert status == 200
            cls.tokens[tenant] = response["access_token"]

    def test_property_lists_are_tenant_scoped(self):
        sunset_status, sunset = request("/dashboard/properties", self.tokens["sunset"])
        ocean_status, ocean = request("/dashboard/properties", self.tokens["ocean"])
        self.assertEqual((sunset_status, ocean_status), (200, 200))
        self.assertEqual({item["name"] for item in sunset}, {
            "Beach House Alpha", "City Apartment Downtown", "Country Villa Estate"
        })
        self.assertEqual({item["name"] for item in ocean}, {
            "Mountain Lodge Beta", "Lakeside Cottage", "Urban Loft Modern"
        })

    def test_march_revenue_and_cache_are_tenant_scoped(self):
        path = "/dashboard/summary?property_id=prop-001&month=3&year=2024"
        for tenant, total, count in (
            ("sunset", "2250.00", 4),
            ("ocean", "0.00", 0),
            ("ocean", "0.00", 0),
            ("sunset", "2250.00", 4),
        ):
            status, summary = request(path, self.tokens[tenant])
            self.assertEqual(status, 200)
            self.assertEqual(summary["total_revenue"], total)
            self.assertEqual(summary["reservations_count"], count)

    def test_local_month_boundary_and_cross_tenant_access(self):
        status, february = request(
            "/dashboard/summary?property_id=prop-001&month=2&year=2024",
            self.tokens["sunset"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(february["total_revenue"], "0.00")

        status, lake = request(
            "/dashboard/summary?property_id=prop-004&month=3&year=2024",
            self.tokens["ocean"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(lake["total_revenue"], "1776.50")
        self.assertEqual(lake["reservations_count"], 4)

        for tenant, property_id in (("ocean", "prop-002"), ("sunset", "prop-004")):
            status, _ = request(
                f"/dashboard/summary?property_id={property_id}&month=3&year=2024",
                self.tokens[tenant],
            )
            self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
