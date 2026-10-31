import unittest

from app import app


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_renders_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"EC2 Fleet Overview", response.data)
        self.assertIn(b"Cloud Monitoring", response.data)

    def test_dashboard_endpoint_returns_sample_payload(self):
        response = self.client.get("/api/dashboard?source=sample&hours=6")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["source"], "sample")
        self.assertEqual(payload["hours"], 6)
        self.assertEqual(len(payload["instances"]), 5)
        self.assertIn("CPUUtilization", payload["series"])
        self.assertIn("totals", payload)

    def test_invalid_query_parameters_are_tolerated(self):
        response = self.client.get("/api/dashboard?hours=abc&source=weird")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["hours"], 24)
        self.assertEqual(payload["requested_source"], "auto")

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_config_endpoint(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("cloudwatch_enabled", payload)
        self.assertIn("region", payload)
        self.assertEqual(payload["max_hours"], 72)


if __name__ == "__main__":
    unittest.main()
