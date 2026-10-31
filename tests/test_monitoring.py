import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import monitoring


class SampleDashboardTests(unittest.TestCase):
    def test_sample_dashboard_shape(self):
        payload = monitoring.dashboard(hours=6, source="sample")

        self.assertEqual(payload["source"], "sample")
        self.assertIsNone(payload["warning"])
        self.assertEqual(payload["hours"], 6)
        self.assertEqual(len(payload["instances"]), len(monitoring.DEMO_INSTANCES))
        self.assertEqual(payload["totals"]["instances"], 5)

        expected_points = 6 * 12 + 1
        self.assertEqual(len(payload["timestamps"]), expected_points)
        for metric in monitoring.METRICS:
            self.assertEqual(
                len(payload["series"][metric["key"]]), expected_points
            )
        self.assertTrue(payload["alerts"])

    def test_requested_instance_is_selected(self):
        target = monitoring.DEMO_INSTANCES[3]["id"]
        payload = monitoring.dashboard(
            hours=1, instance_id=target, source="sample"
        )
        self.assertEqual(payload["selected_instance"], target)
        self.assertEqual(payload["selected_name"], "db-replica-04")

    def test_unknown_instance_falls_back_to_first(self):
        payload = monitoring.dashboard(
            hours=1, instance_id="i-does-not-exist", source="sample"
        )
        self.assertEqual(
            payload["selected_instance"], monitoring.DEMO_INSTANCES[0]["id"]
        )

    def test_hours_are_clamped(self):
        payload = monitoring.dashboard(hours=500, source="sample")
        self.assertEqual(payload["hours"], monitoring.MAX_HOURS)

        payload = monitoring.dashboard(hours=-10, source="sample")
        self.assertEqual(payload["hours"], 1)


class CloudWatchFallbackTests(unittest.TestCase):
    def test_disabled_cloudwatch_falls_back_to_sample(self):
        with patch.dict(os.environ, {"CLOUDWATCH_ENABLED": "false"}):
            payload = monitoring.dashboard(hours=1, source="cloudwatch")

        self.assertEqual(payload["source"], "sample")
        self.assertEqual(payload["requested_source"], "cloudwatch")
        self.assertIn("CloudWatch is disabled", payload["warning"])

    def test_live_provider_failure_falls_back_to_sample(self):
        def boom(*_args, **_kwargs):
            raise monitoring.MonitoringError("AWS is unavailable")

        with (
            patch.dict(os.environ, {"CLOUDWATCH_ENABLED": "true"}),
            patch.object(monitoring, "_cloudwatch_dashboard", side_effect=boom),
        ):
            payload = monitoring.dashboard(hours=1, source="auto")

        self.assertEqual(payload["source"], "sample")
        self.assertIn("AWS is unavailable", payload["warning"])


class FakeCloudWatchClient:
    def __init__(self):
        self.timestamps = [
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 10, 5, tzinfo=UTC),
        ]

    def get_metric_data(self, **kwargs):
        results = []
        for query in kwargs["MetricDataQueries"]:
            name = query["MetricStat"]["Metric"]["MetricName"]
            values = (
                [1048576.0, 2097152.0]
                if name in {"NetworkIn", "NetworkOut"}
                else [12.0, 24.0]
            )
            results.append(
                {
                    "Id": query["Id"],
                    "Timestamps": self.timestamps,
                    "Values": values,
                }
            )
        return {"MetricDataResults": results}


class CloudWatchSeriesTests(unittest.TestCase):
    def test_network_bytes_are_converted_to_megabytes(self):
        instance = monitoring.DEMO_INSTANCES[0]
        timestamps, series = monitoring._cloudwatch_series(
            FakeCloudWatchClient(), [instance], hours=1
        )

        self.assertEqual(len(timestamps), 2)
        self.assertEqual(series[instance["id"]]["CPUUtilization"], [12.0, 24.0])
        self.assertEqual(series[instance["id"]]["NetworkIn"], [1.0, 2.0])
        self.assertEqual(series[instance["id"]]["NetworkOut"], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
