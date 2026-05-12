# KUKA EIP Monitoring

Polls a KUKA robot over EtherNet/IP (CIP), parses the assembly data, and writes to InfluxDB v2. Grafana is used for visualization. The stack runs locally via Docker Compose.

---

## Architecture

```
KUKA Robot (EIP) ──► main_influxV2.py ──► InfluxDB 2.7.1 ◄── Grafana
                         (Python)              (Docker)         (Docker)
```

---

## Requirements

- Docker Desktop
- Python 3.12
- [uv](https://github.com/astral-sh/uv) (included in `installer/`)

---

## Quick Start

### 1. Start InfluxDB + Grafana

```powershell
docker compose up -d
```

| Service  | URL                   | Default Credentials  |
|----------|-----------------------|----------------------|
| InfluxDB | http://localhost:8086 | admin / admin1234    |
| Grafana  | http://localhost:3000 | admin / admin        |

### 2. Install Python dependencies

```powershell
uv sync
```

### 3. Configure `config.json`

Edit the `influxdb` array to set your endpoints, token, org, bucket, and robot ID:

```json
"influxdb": [
    {
        "host": "http://localhost:8086",
        "token": "qwer1234",
        "org": "iot-predictive",
        "database": "kuka-data",
        "robot_id": "calul_033"
    }
]
```

To write to **multiple endpoints simultaneously**, add more objects to the array:

```json
"influxdb": [
    {
        "host": "http://localhost:8086",
        "token": "qwer1234",
        "org": "iot-predictive",
        "database": "kuka-data",
        "robot_id": "calul_033"
    },
    {
        "host": "https://your-remote-server/influxdb",
        "token": "your-token",
        "org": "iot-predictive",
        "database": "kuka-data",
        "robot_id": "calul_033"
    }
]
```

Each endpoint is written to independently — one failure does not affect the others.

### 4. Run the monitor

```powershell
run_scripts.bat
```

Or directly:

```powershell
uv run main_influxV2.py
```

To stop:

```powershell
stop_scripts.bat
```

---

## Configuration Reference

### `config.json`

| Key | Description |
|-----|-------------|
| `kuka.ip` | Robot IP address |
| `kuka.port` | EIP port (default 250) |
| `kuka.assembly_input` | Assembly object instance number |
| `influxdb[].host` | InfluxDB URL |
| `influxdb[].token` | InfluxDB API token |
| `influxdb[].org` | InfluxDB organization |
| `influxdb[].database` | Bucket name |
| `influxdb[].robot_id` | Tag value written with every point |
| `poll_interval_s` | Polling interval in seconds (default 0.1) |

---

## InfluxDB Data Schema

### Measurement: `kuka_robot`
Written every poll cycle.

| Tag | Value |
|-----|-------|
| `robot_id` | from config (e.g. `calul_033`) |

| Field | Unit | Description |
|-------|------|-------------|
| `TEMP_A1_cel` ~ `TEMP_A6_cel` | °C | Joint temperatures (converted from Kelvin) |
| `ROB_RUNTIME` | — | Robot runtime counter |
| `isPick`, `isPlace`, `isDriveOn`, `isError`, `isMoving`, `isProgramRunning` | 0/1 | Status bits |
| `override` | % | Speed override |
| `acc_a/b/c`, `acc_x/y/z` | — | Axis accelerations |
| `vel_a/b/c`, `vel_x/y/z` | — | Axis velocities |

### Measurement: `kuka_points`
Written only on rising edge of `isPick` or `isPlace`.

| Tag | Value |
|-----|-------|
| `robot_id` | from config |
| `event` | `pick` or `place` |

| Field | Unit |
|-------|------|
| `X_mm`, `Y_mm`, `Z_mm` | mm |
| `A_deg`, `B_deg`, `C_deg` | degrees |

---

## Grafana Setup

1. Open http://localhost:3000 → **Connections → Data Sources → Add data source → InfluxDB**
2. Set **Query Language** to `Flux`
3. Fill in:

| Field | Value |
|-------|-------|
| URL | `http://influxdb:8086` |
| Organization | `iot-predictive` |
| Token | `qwer1234` |
| Default Bucket | `kuka-data` |

4. Click **Save & Test**

### Example Flux Query

```flux
from(bucket: "kuka-data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kuka_robot")
  |> filter(fn: (r) => r.robot_id == "calul_033")
  |> filter(fn: (r) => r._field == "TEMP_A1_cel")
```

---

## Stop / Teardown

Stop containers (keep data):
```powershell
docker compose down
```

Stop and remove all data volumes:
```powershell
docker compose down -v
```
