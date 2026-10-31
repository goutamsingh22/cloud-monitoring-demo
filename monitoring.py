"""Metric providers for the Cloud Monitoring demo.

The demo works out of the box with deterministic sample EC2 metrics. When
CloudWatch is explicitly enabled, live metrics are pulled with boto3 and the
sample data is used as a graceful fallback if the AWS call fails.
"""

from __future__ import annotations

import math
import os
import random
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - boto3 is optional at runtime
    boto3 = None
    BotoCoreError = ClientError = Exception

PERIOD_SECONDS = 300
MAX_HOURS = 72
MAX_CLOUDWATCH_INSTANCES = 20

METRICS = [
    {
        "key": "CPUUtilization",
        "label": "CPU Utilization",
        "unit": "%",
        "color": "#6c8cff",
    },
    {
        "key": "NetworkIn",
        "label": "Network In",
        "unit": "MB",
        "color": "#22c55e",
    },
    {
        "key": "NetworkOut",
        "label": "Network Out",
        "unit": "MB",
        "color": "#f59e0b",
    },
    {
        "key": "DiskReadOps",
        "label": "Disk Read Ops",
        "unit": "ops/s",
        "color": "#a78bfa",
    },
]

METRIC_LOOKUP = {metric["key"]: metric for metric in METRICS}

DEMO_INSTANCES = [
    {
        "id": "i-0a1b2c3d4e5f60001",
        "name": "web-prod-01",
        "type": "t3.medium",
        "az": "us-east-1a",
        "state": "running",
        "base_cpu": 34,
        "cpu_amplitude": 15,
        "phase": 0.4,
        "network_in": 1.6,
        "network_out": 0.9,
        "disk_ops": 12,
    },
    {
        "id": "i-0a1b2c3d4e5f60002",
        "name": "api-prod-02",
        "type": "c6i.large",
        "az": "us-east-1b",
        "state": "running",
        "base_cpu": 58,
        "cpu_amplitude": 18,
        "phase": 1.7,
        "network_in": 2.9,
        "network_out": 1.7,
        "disk_ops": 21,
    },
    {
        "id": "i-0a1b2c3d4e5f60003",
        "name": "worker-03",
        "type": "m5.large",
        "az": "us-east-1c",
        "state": "running",
        "base_cpu": 72,
        "cpu_amplitude": 12,
        "phase": 3.1,
        "network_in": 3.6,
        "network_out": 2.4,
        "disk_ops": 34,
    },
    {
        "id": "i-0a1b2c3d4e5f60004",
        "name": "db-replica-04",
        "type": "r6i.xlarge",
        "az": "us-east-1a",
        "state": "running",
        "base_cpu": 46,
        "cpu_amplitude": 9,
        "phase": 4.2,
        "network_in": 5.2,
        "network_out": 4.8,
        "disk_ops": 44,
    },
    {
        "id": "i-0a1b2c3d4e5f60005",
        "name": "batch-runner-05",
        "type": "t3.small",
        "az": "us-east-1d",
        "state": "running",
        "base_cpu": 24,
        "cpu_amplitude": 27,
        "phase": 5.4,
        "network_in": 0.8,
        "network_out": 0.5,
        "disk_ops": 8,
    },
]


class MonitoringError(RuntimeError):
    """Raised when live metrics cannot be loaded."""


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def cloudwatch_enabled() -> bool:
    return _env_flag("CLOUDWATCH_ENABLED")


def region_name() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


def _sample_timeline(hours: int) -> list[datetime]:
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 5)
    start = end - timedelta(hours=hours)
    points = int((end - start).total_seconds() // PERIOD_SECONDS) + 1
    return [start + timedelta(seconds=PERIOD_SECONDS * i) for i in range(points)]


def _sample_series(instance: dict[str, Any], metric: str, count: int) -> list[float]:
    rng = random.Random(f"{instance['id']}:{metric}")
    phase = instance["phase"]
    values: list[float] = []

    for index in range(count):
        wave = math.sin(index / 12 + phase)
        drift = math.sin(index / 55 + phase / 2)
        if metric == "CPUUtilization":
            value = (
                instance["base_cpu"]
                + wave * instance["cpu_amplitude"]
                + drift * instance["cpu_amplitude"] * 0.35
                + rng.uniform(-4, 4)
            )
            if rng.random() < 0.012:
                value += rng.uniform(22, 48)
            value = _clamp(value, 2, 99)
        elif metric == "NetworkIn":
            value = instance["network_in"] * (1 + wave * 0.35 + drift * 0.15)
            value += rng.uniform(-0.18, 0.18)
            if rng.random() < 0.01:
                value *= rng.uniform(1.6, 2.4)
            value = max(0.02, value)
        elif metric == "NetworkOut":
            value = instance["network_out"] * (1 + wave * 0.4 + drift * 0.12)
            value += rng.uniform(-0.12, 0.12)
            if rng.random() < 0.01:
                value *= rng.uniform(1.5, 2.2)
            value = max(0.01, value)
        else:
            value = instance["disk_ops"] * (1 + wave * 0.3)
            value += rng.uniform(-2.5, 2.5)
            if rng.random() < 0.015:
                value += rng.uniform(18, 40)
            value = max(0.5, value)

        values.append(_round(value, 2))

    return values


def _instance_summary(instance: dict[str, Any], series: dict[str, list[float]]) -> dict:
    cpu = series["CPUUtilization"]
    network = [
        inbound + outbound
        for inbound, outbound in zip(series["NetworkIn"], series["NetworkOut"])
    ]
    peak_cpu = max(cpu)
    avg_cpu = _mean(cpu)
    if peak_cpu >= 90:
        health = "critical"
    elif peak_cpu >= 78:
        health = "warning"
    else:
        health = "healthy"
    return {
        "id": instance["id"],
        "name": instance["name"],
        "type": instance["type"],
        "az": instance["az"],
        "state": instance["state"],
        "avg_cpu": _round(avg_cpu),
        "peak_cpu": _round(peak_cpu),
        "avg_network": _round(_mean(network), 2),
        "health": health,
    }


def _build_alerts(
    instances: list[dict[str, Any]],
    all_series: dict[str, dict[str, list[float | None]]],
    timestamps: list[datetime],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for instance in instances:
        series = all_series[instance["id"]]
        cpu_points = [
            (index, value)
            for index, value in enumerate(series["CPUUtilization"])
            if value is not None
        ]
        if not cpu_points:
            continue
        peak_index, peak_cpu = max(cpu_points, key=lambda item: item[1])
        avg_cpu = _mean([value for _, value in cpu_points])

        if peak_cpu >= 90:
            alerts.append(
                {
                    "severity": "critical",
                    "instance": instance["name"],
                    "instance_id": instance["id"],
                    "metric": "CPUUtilization",
                    "message": (
                        f"CPU peaked at {peak_cpu:.1f}% "
                        f"(average {avg_cpu:.1f}%)"
                    ),
                    "timestamp": _iso(timestamps[peak_index]),
                    "value": _round(peak_cpu),
                }
            )
        elif peak_cpu >= 78:
            alerts.append(
                {
                    "severity": "warning",
                    "instance": instance["name"],
                    "instance_id": instance["id"],
                    "metric": "CPUUtilization",
                    "message": (
                        f"CPU reached {peak_cpu:.1f}% "
                        f"(average {avg_cpu:.1f}%)"
                    ),
                    "timestamp": _iso(timestamps[peak_index]),
                    "value": _round(peak_cpu),
                }
            )

        network_points = [
            (index, value)
            for index, value in enumerate(series["NetworkIn"])
            if value is not None
        ]
        if not network_points:
            continue
        peak_net_index, peak_net = max(network_points, key=lambda item: item[1])
        avg_net = _mean([value for _, value in network_points])
        if peak_net > max(avg_net * 1.8, 0.5):
            alerts.append(
                {
                    "severity": "info",
                    "instance": instance["name"],
                    "instance_id": instance["id"],
                    "metric": "NetworkIn",
                    "message": (
                        f"Network ingress spike of {peak_net:.2f} MB "
                        f"(average {avg_net:.2f} MB)"
                    ),
                    "timestamp": _iso(timestamps[peak_net_index]),
                    "value": _round(peak_net, 2),
                }
            )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda item: (severity_rank[item["severity"]], item["timestamp"]))
    return alerts[:12]


def _sample_dashboard(
    hours: int, instance_id: str | None
) -> dict[str, Any]:
    timestamps = _sample_timeline(hours)
    all_series: dict[str, dict[str, list[float]]] = {}
    for instance in DEMO_INSTANCES:
        all_series[instance["id"]] = {
            metric["key"]: _sample_series(instance, metric["key"], len(timestamps))
            for metric in METRICS
        }

    instances = [
        _instance_summary(instance, all_series[instance["id"]])
        for instance in DEMO_INSTANCES
    ]
    selected = instance_id if instance_id in all_series else DEMO_INSTANCES[0]["id"]
    selected_instance = next(inst for inst in DEMO_INSTANCES if inst["id"] == selected)
    alerts = _build_alerts(DEMO_INSTANCES, all_series, timestamps)

    return {
        "source": "sample",
        "region": region_name(),
        "generated_at": _iso(datetime.now(UTC)),
        "period_seconds": PERIOD_SECONDS,
        "hours": hours,
        "instances": instances,
        "selected_instance": selected,
        "selected_name": selected_instance["name"],
        "timestamps": [_iso(point) for point in timestamps],
        "metrics": METRICS,
        "series": all_series[selected],
        "alerts": alerts,
        "totals": {
            "instances": len(instances),
            "avg_cpu": _round(_mean([item["avg_cpu"] for item in instances])),
            "peak_cpu": _round(max(item["peak_cpu"] for item in instances)),
            "alerts": len(alerts),
            "healthy": sum(1 for item in instances if item["health"] == "healthy"),
        },
    }


def _cloudwatch_client(region: str):
    if boto3 is None:
        raise MonitoringError(
            "boto3 is not installed. Run: pip install -r requirements.txt"
        )
    try:
        return boto3.session.Session(region_name=region).client("cloudwatch")
    except (BotoCoreError, ClientError) as exc:
        raise MonitoringError(f"Could not create CloudWatch client: {exc}") from exc


def _cloudwatch_instances(region: str) -> list[dict[str, Any]]:
    raw_ids = os.environ.get("EC2_INSTANCE_IDS", "").strip()
    if raw_ids:
        ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        if not ids:
            raise MonitoringError("EC2_INSTANCE_IDS is empty.")
        return [
            {
                "id": instance_id,
                "name": instance_id,
                "type": "from EC2_INSTANCE_IDS",
                "az": "-",
                "state": "unknown",
            }
            for instance_id in ids[:MAX_CLOUDWATCH_INSTANCES]
        ]

    try:
        ec2 = boto3.session.Session(region_name=region).client("ec2")
        paginator = ec2.get_paginator("describe_instances")
        pages = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
        instances: list[dict[str, Any]] = []
        for page in pages:
            for reservation in page.get("Reservations", []):
                for item in reservation.get("Instances", []):
                    tags = {tag["Key"]: tag["Value"] for tag in item.get("Tags", [])}
                    instances.append(
                        {
                            "id": item["InstanceId"],
                            "name": tags.get("Name", item["InstanceId"]),
                            "type": item.get("InstanceType", "unknown"),
                            "az": item.get("Placement", {}).get(
                                "AvailabilityZone", "-"
                            ),
                            "state": item.get("State", {}).get("Name", "unknown"),
                        }
                    )
                    if len(instances) >= MAX_CLOUDWATCH_INSTANCES:
                        return instances
    except (BotoCoreError, ClientError) as exc:
        raise MonitoringError(
            "Could not list EC2 instances. Set EC2_INSTANCE_IDS to skip "
            f"DescribeInstances. ({exc})"
        ) from exc

    if not instances:
        raise MonitoringError(
            "No running EC2 instances were found in this account/region."
        )
    return instances


def _cloudwatch_series(
    client: Any, instances: list[dict[str, Any]], hours: int
) -> tuple[list[datetime], dict[str, dict[str, list[float | None]]]]:
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - timedelta(hours=hours)

    queries: list[dict[str, Any]] = []
    lookup: dict[str, tuple[str, str]] = {}
    for instance in instances:
        for metric in METRICS:
            query_id = f"m{len(queries)}"
            queries.append(
                {
                    "Id": query_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EC2",
                            "MetricName": metric["key"],
                            "Dimensions": [
                                {"Name": "InstanceId", "Value": instance["id"]}
                            ],
                        },
                        "Period": PERIOD_SECONDS,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )
            lookup[query_id] = (instance["id"], metric["key"])

    collected: dict[str, dict[datetime, float]] = {}
    next_token = None
    while True:
        request: dict[str, Any] = {
            "MetricDataQueries": queries,
            "StartTime": start,
            "EndTime": end,
            "ScanBy": "TimestampAscending",
        }
        if next_token:
            request["NextToken"] = next_token
        try:
            response = client.get_metric_data(**request)
        except (BotoCoreError, ClientError) as exc:
            raise MonitoringError(f"CloudWatch request failed: {exc}") from exc

        for result in response.get("MetricDataResults", []):
            bucket = collected.setdefault(result["Id"], {})
            for timestamp, value in zip(
                result.get("Timestamps", []), result.get("Values", [])
            ):
                bucket[timestamp] = value

        next_token = response.get("NextToken")
        if not next_token:
            break

    timestamps = sorted(
        {timestamp for bucket in collected.values() for timestamp in bucket}
    )
    series: dict[str, dict[str, list[float | None]]] = {
        instance["id"]: {metric["key"]: [] for metric in METRICS}
        for instance in instances
    }

    for instance in instances:
        for metric in METRICS:
            query_id = next(
                key
                for key, target in lookup.items()
                if target == (instance["id"], metric["key"])
            )
            bucket = collected.get(query_id, {})
            values: list[float | None] = []
            for timestamp in timestamps:
                value = bucket.get(timestamp)
                if value is None:
                    values.append(None)
                    continue
                if metric["key"] in {"NetworkIn", "NetworkOut"}:
                    value = value / (1024 * 1024)
                values.append(_round(value, 2))
            series[instance["id"]][metric["key"]] = values

    return timestamps, series


def _cloudwatch_dashboard(
    hours: int, instance_id: str | None
) -> dict[str, Any]:
    region = region_name()
    client = _cloudwatch_client(region)
    instances = _cloudwatch_instances(region)
    timestamps, raw_series = _cloudwatch_series(client, instances, hours)

    if not timestamps:
        raise MonitoringError(
            "CloudWatch returned no datapoints for the selected instances. "
            "Check the metric period and that the instances are publishing metrics."
        )

    summaries: list[dict[str, Any]] = []
    all_series: dict[str, dict[str, list[float]]] = {}
    for instance in instances:
        numeric: dict[str, list[float]] = {}
        for metric in METRICS:
            numeric[metric["key"]] = [
                value for value in raw_series[instance["id"]][metric["key"]]
                if value is not None
            ]
        if not numeric["CPUUtilization"]:
            continue
        all_series[instance["id"]] = numeric
        summaries.append(_instance_summary(instance, numeric))

    if not summaries:
        raise MonitoringError(
            "CloudWatch returned no CPU data for the selected instances."
        )

    available = [instance for instance in instances if instance["id"] in all_series]
    selected = instance_id if instance_id in all_series else available[0]["id"]
    selected_meta = next(inst for inst in available if inst["id"] == selected)
    alerts = _build_alerts(available, raw_series, timestamps)

    return {
        "source": "cloudwatch",
        "region": region,
        "generated_at": _iso(datetime.now(UTC)),
        "period_seconds": PERIOD_SECONDS,
        "hours": hours,
        "instances": summaries,
        "selected_instance": selected,
        "selected_name": selected_meta["name"],
        "timestamps": [_iso(point) for point in timestamps],
        "metrics": METRICS,
        "series": raw_series[selected],
        "alerts": alerts,
        "totals": {
            "instances": len(summaries),
            "avg_cpu": _round(_mean([item["avg_cpu"] for item in summaries])),
            "peak_cpu": _round(max(item["peak_cpu"] for item in summaries)),
            "alerts": len(alerts),
            "healthy": sum(
                1 for item in summaries if item["health"] == "healthy"
            ),
        },
    }


def dashboard(
    hours: int = 24,
    instance_id: str | None = None,
    source: str = "auto",
) -> dict[str, Any]:
    """Return dashboard data, falling back to sample metrics on AWS errors."""
    hours = max(1, min(MAX_HOURS, int(hours)))
    source = (source or "auto").lower()
    warning = None

    use_cloudwatch = source == "cloudwatch" or (
        source == "auto" and cloudwatch_enabled()
    )

    if use_cloudwatch:
        if not cloudwatch_enabled():
            warning = (
                "CloudWatch is disabled. Set CLOUDWATCH_ENABLED=true (and AWS "
                "credentials) to query live metrics. Showing sample data."
            )
        else:
            try:
                payload = _cloudwatch_dashboard(hours, instance_id)
                payload["requested_source"] = source
                payload["warning"] = None
                return payload
            except MonitoringError as exc:
                warning = f"{exc} Showing sample data instead."

    payload = _sample_dashboard(hours, instance_id)
    payload["requested_source"] = source
    payload["warning"] = warning
    return payload
