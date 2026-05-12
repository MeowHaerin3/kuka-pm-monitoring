import json
import logging
import time
import struct
import socket
import urllib.request
import urllib.error
from typing import Any, Generator
from pycomm3 import CIPDriver
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import colorama
from colorama import Fore, Style

colorama.init()

# ── Logging setup ──────────────────────────────────────────
_LEVEL_COLORS = {
    logging.DEBUG:    Fore.WHITE,
    logging.INFO:     Fore.CYAN,
    logging.WARNING:  Fore.YELLOW,
    logging.ERROR:    Fore.RED,
    logging.CRITICAL: Fore.MAGENTA,
}

class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, Fore.WHITE)
        tag   = f"{color}[{record.levelname}]{Style.RESET_ALL}"
        ts    = self.formatTime(record, self.datefmt)
        return f"{ts} {tag} {record.getMessage()}"

_handler = logging.StreamHandler()
_handler.setFormatter(_ColorFormatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logging.getLogger("pycomm3").setLevel(logging.WARNING)
logging.getLogger("influxdb_client").setLevel(logging.WARNING)
log = logging.getLogger("kuka")

# ── Constants ──────────────────────────────────────────────
TYPE_SIZE = {
    "BOOL":  0,
    "BYTE":  1,
    "WORD":  2,
    "DWORD": 4,
    "DINT":  4,
    "REAL":  4,
}

SCALE_1000 = {
    "X": "X_mm", "Y": "Y_mm", "Z": "Z_mm",
    "A": "A_deg", "B": "B_deg", "C": "C_deg",
}

KELVIN_TO_C = {
    "TEMP_A1": "TEMP_A1_cel", "TEMP_A2": "TEMP_A2_cel", "TEMP_A3": "TEMP_A3_cel",
    "TEMP_A4": "TEMP_A4_cel", "TEMP_A5": "TEMP_A5_cel", "TEMP_A6": "TEMP_A6_cel",
}

RETRY_DELAYS = [1, 2, 5, 10, 30]


# ── Offset map ─────────────────────────────────────────────
def build_offset_map(assembly_map: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    for entry in assembly_map:
        name, addr = entry["name"], str(entry["addr"])
        if name in seen:
            raise ValueError(
                f"duplicate signal name '{name}' in assembly_map "
                f"(addr {seen[name]} vs {addr})"
            )
        seen[name] = addr

    result = []
    for entry in assembly_map:
        addr = str(entry["addr"])
        if entry["type"] == "BOOL":
            byte_str, bit_str = addr.split(".")
            result.append({
                **entry,
                "byte_offset": int(byte_str),
                "bit_index": int(bit_str),
            })
        else:
            result.append({
                **entry,
                "byte_offset": int(addr),
                "bit_index": None,
            })
    return result


# ── Parser ─────────────────────────────────────────────────
def parse_raw(raw: bytes, offset_map: list[dict]) -> dict[str, Any]:
    values = {}
    for entry in offset_map:
        name, dtype, offset = entry["name"], entry["type"], entry["byte_offset"]
        if dtype == "BOOL":
            values[name] = bool((raw[offset] >> entry["bit_index"]) & 1)
        elif dtype == "BYTE":
            values[name] = raw[offset]
        elif dtype == "WORD":
            values[name] = struct.unpack_from("<H", raw, offset)[0]
        elif dtype == "DWORD":
            values[name] = struct.unpack_from("<I", raw, offset)[0]
        elif dtype == "DINT":
            values[name] = struct.unpack_from("<i", raw, offset)[0]
        elif dtype == "REAL":
            values[name] = struct.unpack_from("<f", raw, offset)[0]

        if name in SCALE_1000:
            values[SCALE_1000[name]] = values.pop(name) / 1000.0
        elif name in KELVIN_TO_C:
            values[KELVIN_TO_C[name]] = int(values.pop(name) - 273)

    return values


# ── Connect + Auto-reconnect ───────────────────────────────
def connect_kuka(
    ip: str,
    assembly_input: int,
    offset_map: list[dict],
) -> Generator[dict, None, None]:

    attempt = 0

    while True:
        delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]

        log.info(f"[CONNECTING] {ip}  (attempt #{attempt + 1})")

        try:
            with CIPDriver(ip) as drive:
                log.info(f"[CONNECTED]  {ip}")
                attempt = 0
                consecutive_errors = 0
                kuka_ok = None

                while True:
                    alive = ping_kuka(ip)
                    if alive != kuka_ok:
                        if alive:
                            log.info(f"[KUKA UP]   {ip} is reachable")
                        else:
                            log.warning(f"[KUKA DOWN] {ip} not reachable — waiting for reconnect")
                        kuka_ok = alive

                    if not kuka_ok:
                        time.sleep(1)
                        continue

                    result = drive.generic_message(
                        service=0x0E,
                        class_code=0x04,
                        instance=assembly_input,
                        attribute=3,
                        connected=False,
                        unconnected_send=False,
                        name="read_assembly",
                    )

                    if not (result and not result.error):
                        consecutive_errors += 1
                        err_msg = result.error if result else "no response"
                        log.warning(f"[READ ERROR] #{consecutive_errors}  reason={err_msg}")
                        if consecutive_errors >= 3:
                            log.error(f"[DISCONNECTED] {consecutive_errors} consecutive errors → reconnect")
                            break
                        time.sleep(0.5)
                        continue

                    consecutive_errors = 0
                    raw  = bytes(result.value)
                    data = parse_raw(raw, offset_map)
                    log.debug(f"[DATA] {data}")
                    yield data

        except Exception as e:
            log.error(f"[CONN FAILED] {ip}  error={e}")

        attempt += 1
        log.info(f"[WAITING]    retry in {delay}s  (attempt #{attempt + 1} next)")
        time.sleep(delay)


# ── Health checks ──────────────────────────────────────────
def ping_kuka(ip: str, port: int = 44818, timeout: int = 2) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def ping_influx(host: str, timeout: int = 2) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/health", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


# ── InfluxDB 2.x write ─────────────────────────────────────
POSITION_FIELDS = {"X_mm", "Y_mm", "Z_mm", "A_deg", "B_deg", "C_deg"}


def write_to_influx(write_api, bucket: str, robot_id: str, data: dict[str, Any]) -> None:
    point = Point("kuka_robot").tag("robot_id", robot_id)
    for key, value in data.items():
        if key in POSITION_FIELDS:
            continue
        if isinstance(value, bool):
            point = point.field(key, int(value))
        elif isinstance(value, float):
            point = point.field(key, float(value))
        else:
            point = point.field(key, value)
    write_api.write(bucket=bucket, record=point)


def write_point_snapshot(write_api, bucket: str, robot_id: str, data: dict[str, Any], event: str) -> None:
    point = Point("kuka_points").tag("robot_id", robot_id).tag("event", event)
    for key in POSITION_FIELDS:
        if key in data:
            point = point.field(key, float(data[key]))
    write_api.write(bucket=bucket, record=point)


# ── Main ───────────────────────────────────────────────────
if __name__ == "__main__":
    with open("config.json") as f:
        cfg = json.load(f)

    offset_map = build_offset_map(cfg["assembly_map"])

    log.info("=== KUKA EIP Monitor starting (InfluxDB 2.x) ===")
    for d in offset_map:
        bit = f", bit={d['bit_index']}" if d["bit_index"] is not None else ""
        log.info(f"  {d['name']:20s} | {d['addr']} | byte={d['byte_offset']}{bit}")

    influx_endpoints = cfg["influxdb"]
    poll_interval    = cfg.get("poll_interval_s", 0.1)

    # build one client+write_api per endpoint
    targets = []
    for endpoint in influx_endpoints:
        client    = InfluxDBClient(url=endpoint["host"], token=endpoint["token"], org=endpoint["org"])
        write_api = client.write_api(write_options=SYNCHRONOUS)
        targets.append({
            "client":    client,
            "write_api": write_api,
            "host":      endpoint["host"],
            "bucket":    endpoint["database"],
            "robot_id":  endpoint["robot_id"],
            "ok":        None,
        })

    prev_is_point = False
    prev_is_place = False

    def write_all(fn, *args):
        for t in targets:
            try:
                fn(t["write_api"], t["bucket"], t["robot_id"], *args)
            except Exception as e:
                log.warning(f"[INFLUX ERROR] {t['host']}  {e}")

    try:
        for data in connect_kuka(
            cfg["kuka"]["ip"],
            cfg["kuka"]["assembly_input"],
            offset_map,
        ):
            for t in targets:
                alive = ping_influx(t["host"])
                if alive != t["ok"]:
                    if alive:
                        log.info(f"[INFLUX UP]   {t['host']}")
                    else:
                        log.warning(f"[INFLUX DOWN] {t['host']} — skipping writes")
                    t["ok"] = alive

            any_ok = any(t["ok"] for t in targets)
            if any_ok:
                for t in targets:
                    if not t["ok"]:
                        continue
                    try:
                        write_to_influx(t["write_api"], t["bucket"], t["robot_id"], data)
                        log.debug(f"[INFLUX] {t['host']} wrote {data}")
                    except Exception as e:
                        log.warning(f"[INFLUX ERROR] {t['host']}  {e}")

                is_point = bool(data.get("isPoint", False))
                is_place = bool(data.get("isPlace", False))

                rising_point = is_point and not prev_is_point
                rising_place = is_place and not prev_is_place

                if rising_point:
                    for t in targets:
                        if not t["ok"]:
                            continue
                        try:
                            write_point_snapshot(t["write_api"], t["bucket"], t["robot_id"], data, event="pick")
                            log.info(f"[PICK] {t['host']} captured pose = "
                                     f"{ {k: data.get(k) for k in POSITION_FIELDS} }")
                        except Exception as e:
                            log.warning(f"[PICK ERROR] {t['host']}  {e}")

                if rising_place:
                    for t in targets:
                        if not t["ok"]:
                            continue
                        try:
                            write_point_snapshot(t["write_api"], t["bucket"], t["robot_id"], data, event="place")
                            log.info(f"[PLACE] {t['host']} captured pose = "
                                     f"{ {k: data.get(k) for k in POSITION_FIELDS} }")
                        except Exception as e:
                            log.warning(f"[PLACE ERROR] {t['host']}  {e}")

                prev_is_point = is_point
                prev_is_place = is_place

            time.sleep(poll_interval)
    finally:
        for t in targets:
            t["write_api"].close()
            t["client"].close()
