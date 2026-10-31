# Pulse — Cloud Monitoring Demo

A self-contained EC2 monitoring dashboard built with **Python**, **Flask**, and
**Boto3**. It ships with deterministic sample EC2 metrics so it runs without an
AWS account, and can optionally stream live metrics from **Amazon CloudWatch**.

![stack](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![stack](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![stack](https://img.shields.io/badge/Boto3-AWS-FF9900?logo=amazonaws&logoColor=white)

## Features

- Fleet overview with per-instance CPU, network, and disk metrics
- Interactive CPU, network throughput, and disk read charts with hover tooltips
- Instance selector, 1h / 6h / 24h / 72h lookback ranges, and auto-refresh
- Threshold-based alerts (critical, warning, informational)
- Fleet health breakdown and instance comparison table
- Dark and light themes with a responsive layout
- **Optional CloudWatch integration** via Boto3 with graceful sample-data fallback

## Quick start

```powershell
cd cloud-monitoring-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8000>.

The dashboard starts in **sample mode**, so no AWS credentials are required.

## Live CloudWatch mode

1. Install the dependencies and configure AWS credentials using the standard
   Boto3 provider chain (`aws configure`, environment variables, SSO, or an IAM
   role).
2. Copy `.env.example` to `.env` or set the variables in your shell.
3. Enable CloudWatch:

```powershell
$env:CLOUDWATCH_ENABLED = "true"
$env:AWS_REGION = "us-east-1"
# Optional: skip DescribeInstances and monitor specific instances
$env:EC2_INSTANCE_IDS = "i-0123456789abcdef0,i-0fedcba9876543210"
python app.py
```

You can also switch the **Source** control in the UI to `CloudWatch`. If AWS is
not configured or a call fails, the dashboard falls back to sample data and
displays the reason in a banner.

### Required IAM permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["cloudwatch:GetMetricData"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances"],
      "Resource": "*"
    }
  ]
}
```

`ec2:DescribeInstances` is only needed when `EC2_INSTANCE_IDS` is empty. The app
caps live monitoring at 20 instances and requests 5-minute `Average` datapoints
from the `AWS/EC2` namespace.

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `CLOUDWATCH_ENABLED` | `false` | Set to `true`, `1`, `yes`, or `on` to use live metrics |
| `AWS_REGION` | `us-east-1` | Region for CloudWatch and EC2 calls |
| `EC2_INSTANCE_IDS` | empty | Comma-separated IDs; skips `DescribeInstances` |
| `PORT` | `8000` | HTTP port |
| `FLASK_DEBUG` | unset | Set to `1` for Flask debug mode |

## API

| Endpoint | Description |
| --- | --- |
| `GET /` | Dashboard UI |
| `GET /api/dashboard?source=auto&hours=24&instance=i-...` | Dashboard payload |
| `GET /api/config` | Data-source and region configuration |
| `GET /api/health` | Health check |

`source` accepts `auto`, `sample`, or `cloudwatch`. `hours` is clamped to 1–72.

Example:

```powershell
curl "http://localhost:8000/api/dashboard?source=sample&hours=6"
```

## Project structure

```
cloud-monitoring-demo/
├── app.py                 # Flask routes
├── monitoring.py          # Sample generator + CloudWatch provider
├── requirements.txt
├── .env.example
├── static/
│   ├── app.js             # Fetching, rendering, SVG charts
│   └── style.css
├── templates/
│   └── index.html
└── tests/
    ├── test_app.py
    └── test_monitoring.py
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests cover the sample generator, CloudWatch fallback behavior, network unit
conversion, and the Flask API. They run offline and never call AWS.

## Notes

- Sample metrics are generated deterministically from each instance ID, so the
  same instance produces a stable baseline while timestamps advance.
- CloudWatch `GetMetricData` requests may incur AWS charges. Keep lookback
  ranges and instance counts small when experimenting.
- The app never stores credentials; Boto3 resolves them through its standard
  provider chain.
