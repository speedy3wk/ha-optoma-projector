#!/usr/bin/env python3
"""Optoma projector HTTP probe.

Collects timing/response data without changing settings by default.
Optional toggle tests for safe actions (Freeze, Info Hide).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

CONTROL_PATH = "/form/control_cgi"
COOKIE = "atop=1"
CMD_QUERY = "QueryControl=QueryControl"
CMD_QUERY_INFO = "QueryInfo=QueryInfo"

# Safe toggles (optional)
TOGGLE_COMMANDS = {
    "freeze": {"command": "freeze=freeze", "state_key": "F0"},
    "info_hide": {"command": "infohide=infohide", "state_key": "F10"},
}

VALUE_NOT_AVAILABLE = "255"


@dataclass
class Sample:
    ts: str
    latency_ms: float
    ok: bool
    error: str | None
    http_status: int | None
    redirect_location: str | None
    response_len: int
    parsed: bool
    parse_error: str | None
    login_like: bool
    data_changed: bool
    changed_keys: int
    power: str | None
    keys: int
    not_available_keys: int
    interval_used: float
    phase: str
    sweep_label: str | None
    request_index: int


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _parse_response(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    json_str = text[start : end + 1]
    json_str = re.sub(r"([,{])\s*([A-Za-z0-9_]+)\s*:", r'\1"\2":', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _is_login_like(text: str) -> bool:
    lower = text.lower()
    return "login" in lower and "password" in lower


async def _post(
    session: aiohttp.ClientSession, url: str, body: str, timeout: int
) -> tuple[str, float, int, str | None]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": COOKIE,
    }
    start = time.perf_counter()
    async with session.post(
        url,
        data=body,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=timeout),
        allow_redirects=False,
    ) as response:
        text = await response.text()
        redirect_location = response.headers.get("Location")
    latency_ms = (time.perf_counter() - start) * 1000.0
    return text, latency_ms, response.status, redirect_location


async def _run_probe(args: argparse.Namespace) -> None:
    url = f"http://{args.host}:{args.port}{CONTROL_PATH}"
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(limit=1, limit_per_host=1)

    samples: list[Sample] = []
    last_data: dict[str, Any] | None = None
    key_stats: dict[str, dict[str, int]] = {}

    start_time = time.monotonic()
    next_info_at = start_time
    interval_used = args.interval
    last_power = None
    request_index = 0

    async with aiohttp.ClientSession(cookie_jar=cookie_jar, connector=connector) as session:
        while True:
            now = time.monotonic()
            elapsed = now - start_time
            if elapsed >= args.duration:
                break

            # Occasional info query
            if now >= next_info_at:
                try:
                    info_text, *_ = await _post(session, url, CMD_QUERY_INFO, args.timeout)
                    info_data = _parse_response(info_text)
                    if info_data:
                        _update_key_stats(key_stats, info_data)
                except Exception:
                    pass
                next_info_at = now + args.info_interval

            ok = True
            error = None
            parsed = False
            parse_error = None
            login_like = False
            data_changed = False
            changed_keys = 0
            power = None
            keys = 0
            response_len = 0
            http_status = None
            redirect_location = None
            not_available_keys = 0

            try:
                text, latency_ms, http_status, redirect_location = await _post(
                    session, url, CMD_QUERY, args.timeout
                )
                response_len = len(text)
                login_like = _is_login_like(text)
                data = _parse_response(text)
                if data is not None:
                    parsed = True
                    keys = len(data)
                    power = data.get("pw")
                    not_available_keys = sum(1 for v in data.values() if v == VALUE_NOT_AVAILABLE)
                    _update_key_stats(key_stats, data)
                    if last_data is not None and data != last_data:
                        data_changed = True
                        changed_keys = sum(
                            1
                            for k, v in data.items()
                            if last_data.get(k) != v
                        )
                        _update_key_changes(key_stats, last_data, data)
                    last_data = data
                    last_power = power
                else:
                    parse_error = "parse_failed"
            except Exception as exc:  # noqa: BLE001
                ok = False
                latency_ms = 0.0
                error = type(exc).__name__
                http_status = None
                redirect_location = None

            samples.append(
                Sample(
                    ts=_now_iso(),
                    latency_ms=latency_ms,
                    ok=ok,
                    error=error,
                    http_status=http_status,
                    redirect_location=redirect_location,
                    response_len=response_len,
                    parsed=parsed,
                    parse_error=parse_error,
                    login_like=login_like,
                    data_changed=data_changed,
                    changed_keys=changed_keys,
                    power=power,
                    keys=keys,
                    not_available_keys=not_available_keys,
                    interval_used=interval_used,
                    phase="poll",
                    sweep_label=None,
                    request_index=request_index,
                )
            )
            request_index += 1

            # Adjust interval based on last known power state (optional)
            if args.adaptive and last_power is not None:
                if last_power in ("2", "3"):
                    interval_used = args.interval_transition
                elif last_power == "0":
                    interval_used = args.interval_standby
                else:
                    interval_used = args.interval_on
            else:
                interval_used = args.interval

            await asyncio.sleep(interval_used)

        if args.toggle_tests:
            for toggle_name, meta in TOGGLE_COMMANDS.items():
                await _run_toggle_test(
                    session,
                    url,
                    toggle_name,
                    meta["command"],
                    meta["state_key"],
                    args.timeout,
                    args.toggle_delay,
                    samples,
                    request_index,
                )
                request_index = len(samples)

        if args.sweep_read:
            await _run_sweep(
                session,
                url,
                args.sweep_intervals,
                args.sweep_count,
                args.timeout,
                samples,
                request_index,
                key_stats,
            )

    _write_log(samples, args.log_file)
    _write_key_stats(key_stats, args.key_stats_file)
    _print_summary(samples)


async def _run_toggle_test(
    session: aiohttp.ClientSession,
    url: str,
    name: str,
    command: str,
    state_key: str,
    timeout: int,
    delay: float,
    samples: list[Sample],
    request_index: int,
) -> None:
    # Read state before
    before_text, before_latency, before_status, before_redirect = await _post(
        session, url, CMD_QUERY, timeout
    )
    before_data = _parse_response(before_text) or {}
    before_val = before_data.get(state_key)
    if before_data:
        _update_key_stats(TOGGLE_KEY_STATS, before_data)

    await _post(session, url, command, timeout)
    await asyncio.sleep(delay)

    after_text, after_latency, after_status, after_redirect = await _post(
        session, url, CMD_QUERY, timeout
    )
    after_data = _parse_response(after_text) or {}
    after_val = after_data.get(state_key)
    if after_data:
        _update_key_stats(TOGGLE_KEY_STATS, after_data)

    # Toggle back if we can infer a change (avoid if unknown/255)
    if before_val not in (None, VALUE_NOT_AVAILABLE) and after_val not in (None, VALUE_NOT_AVAILABLE):
        if before_val != after_val:
            await _post(session, url, command, timeout)
            await asyncio.sleep(delay)

    samples.append(
        Sample(
            ts=_now_iso(),
            latency_ms=before_latency,
            ok=True,
            error=None,
            http_status=before_status,
            redirect_location=before_redirect,
            response_len=len(before_text),
            parsed=_parse_response(before_text) is not None,
            parse_error=None,
            login_like=_is_login_like(before_text),
            data_changed=True,
            changed_keys=0,
            power=before_data.get("pw"),
            keys=len(before_data),
            not_available_keys=sum(1 for v in before_data.values() if v == VALUE_NOT_AVAILABLE),
            interval_used=0.0,
            phase=f"toggle:{name}",
            sweep_label=None,
            request_index=request_index,
        )
    )

    samples.append(
        Sample(
            ts=_now_iso(),
            latency_ms=after_latency,
            ok=True,
            error=None,
            http_status=after_status,
            redirect_location=after_redirect,
            response_len=len(after_text),
            parsed=_parse_response(after_text) is not None,
            parse_error=None,
            login_like=_is_login_like(after_text),
            data_changed=True,
            changed_keys=0,
            power=after_data.get("pw"),
            keys=len(after_data),
            not_available_keys=sum(1 for v in after_data.values() if v == VALUE_NOT_AVAILABLE),
            interval_used=0.0,
            phase=f"toggle:{name}",
            sweep_label=None,
            request_index=request_index + 1,
        )
    )


async def _run_sweep(
    session: aiohttp.ClientSession,
    url: str,
    intervals: list[float],
    count: int,
    timeout: int,
    samples: list[Sample],
    request_index: int,
    key_stats: dict[str, dict[str, int]],
) -> None:
    last_data: dict[str, Any] | None = None
    idx = request_index
    for interval in intervals:
        label = f"{interval:.3f}s"
        for _ in range(count):
            ok = True
            error = None
            parsed = False
            parse_error = None
            login_like = False
            data_changed = False
            changed_keys = 0
            power = None
            keys = 0
            response_len = 0
            http_status = None
            redirect_location = None
            not_available_keys = 0

            try:
                text, latency_ms, http_status, redirect_location = await _post(
                    session, url, CMD_QUERY, timeout
                )
                response_len = len(text)
                login_like = _is_login_like(text)
                data = _parse_response(text)
                if data is not None:
                    parsed = True
                    keys = len(data)
                    power = data.get("pw")
                    not_available_keys = sum(
                        1 for v in data.values() if v == VALUE_NOT_AVAILABLE
                    )
                    _update_key_stats(key_stats, data)
                    if last_data is not None and data != last_data:
                        data_changed = True
                        changed_keys = sum(
                            1
                            for k, v in data.items()
                            if last_data.get(k) != v
                        )
                        _update_key_changes(key_stats, last_data, data)
                    last_data = data
                else:
                    parse_error = "parse_failed"
            except Exception as exc:  # noqa: BLE001
                ok = False
                latency_ms = 0.0
                error = type(exc).__name__

            samples.append(
                Sample(
                    ts=_now_iso(),
                    latency_ms=latency_ms,
                    ok=ok,
                    error=error,
                    http_status=http_status,
                    redirect_location=redirect_location,
                    response_len=response_len,
                    parsed=parsed,
                    parse_error=parse_error,
                    login_like=login_like,
                    data_changed=data_changed,
                    changed_keys=changed_keys,
                    power=power,
                    keys=keys,
                    not_available_keys=not_available_keys,
                    interval_used=interval,
                    phase="sweep",
                    sweep_label=label,
                    request_index=idx,
                )
            )
            idx += 1
            await asyncio.sleep(interval)


def _write_log(samples: list[Sample], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s.__dict__, ensure_ascii=False) + "\n")


def _print_summary(samples: list[Sample]) -> None:
    latencies = [s.latency_ms for s in samples if s.ok and s.latency_ms > 0]
    errors = [s for s in samples if not s.ok or s.parse_error]
    login_hits = sum(1 for s in samples if s.login_like)
    parsed_ok = sum(1 for s in samples if s.parsed)
    redirects = sum(1 for s in samples if s.redirect_location)
    avg_keys = statistics.mean([s.keys for s in samples if s.keys > 0]) if samples else 0
    avg_na = statistics.mean(
        [s.not_available_keys for s in samples if s.keys > 0]
    ) if samples else 0

    if latencies:
        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[-1]
        avg = statistics.mean(latencies)
    else:
        p50 = p95 = avg = 0.0

    print("Probe summary")
    print(f"  Samples: {len(samples)}")
    print(f"  Parsed OK: {parsed_ok}")
    print(f"  Errors/parse failures: {len(errors)}")
    print(f"  Login-like responses: {login_hits}")
    print(f"  Redirects: {redirects}")
    print(f"  Avg keys / NA-keys: {avg_keys:.1f} / {avg_na:.1f}")
    print(f"  Latency ms avg/p50/p95: {avg:.1f}/{p50:.1f}/{p95:.1f}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optoma projector HTTP probe (non-invasive by default)."
    )
    parser.add_argument("--host", required=True, help="Projector IP or hostname")
    parser.add_argument("--port", type=int, default=80, help="HTTP port (default 80)")
    parser.add_argument("--duration", type=int, default=180, help="Duration in seconds")
    parser.add_argument("--interval", type=float, default=4.0, help="Polling interval in seconds")
    parser.add_argument("--interval-on", type=float, default=4.0, help="Interval when power is ON")
    parser.add_argument("--interval-standby", type=float, default=10.0, help="Interval when standby")
    parser.add_argument("--interval-transition", type=float, default=2.0, help="Interval when warming/cooling")
    parser.add_argument("--timeout", type=int, default=6, help="Request timeout in seconds")
    parser.add_argument("--info-interval", type=int, default=60, help="QueryInfo interval in seconds")
    parser.add_argument("--log-file", default="projector_probe.log", help="Log file path")
    parser.add_argument(
        "--adaptive",
        action="store_true",
        default=True,
        help="Adapt interval based on power state (standby/transition/on)",
    )
    parser.add_argument(
        "--no-adaptive",
        action="store_false",
        dest="adaptive",
        help="Disable adaptive intervals",
    )
    parser.add_argument(
        "--toggle-tests",
        action="store_true",
        default=True,
        help="Run safe toggle tests (freeze/info_hide) and revert",
    )
    parser.add_argument(
        "--no-toggle-tests",
        action="store_false",
        dest="toggle_tests",
        help="Disable toggle tests",
    )
    parser.add_argument(
        "--toggle-delay",
        type=float,
        default=2.5,
        help="Seconds to wait after toggle before re-check",
    )
    parser.add_argument(
        "--sweep-read",
        action="store_true",
        default=True,
        help="Run a read-only sweep with burst queries at multiple intervals",
    )
    parser.add_argument(
        "--no-sweep-read",
        action="store_false",
        dest="sweep_read",
        help="Disable read-only sweep",
    )
    parser.add_argument(
        "--sweep-count",
        type=int,
        default=8,
        help="Number of queries per sweep interval",
    )
    parser.add_argument(
        "--sweep-intervals",
        type=_parse_intervals,
        default="0.1,0.2,0.5,1,2",
        help="Comma-separated sweep intervals in seconds",
    )
    parser.add_argument(
        "--key-stats-file",
        default="projector_probe_keys.json",
        help="Path for key inventory stats JSON",
    )
    return parser


def _parse_intervals(raw: str) -> list[float]:
    items = [s.strip() for s in raw.split(",") if s.strip()]
    intervals: list[float] = []
    for item in items:
        try:
            intervals.append(float(item))
        except ValueError:
            continue
    return intervals or [0.1, 0.2, 0.5, 1.0, 2.0]


TOGGLE_KEY_STATS: dict[str, dict[str, int]] = {}


def _update_key_stats(stats: dict[str, dict[str, int]], data: dict[str, Any]) -> None:
    for key, value in data.items():
        entry = stats.setdefault(key, {"seen": 0, "na": 0, "changed": 0})
        entry["seen"] += 1
        if value == VALUE_NOT_AVAILABLE:
            entry["na"] += 1


def _update_key_changes(
    stats: dict[str, dict[str, int]],
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    for key, after_val in after.items():
        if before.get(key) != after_val:
            entry = stats.setdefault(key, {"seen": 0, "na": 0, "changed": 0})
            entry["changed"] += 1


def _write_key_stats(stats: dict[str, dict[str, int]], path: str) -> None:
    output = {"keys": stats, "generated_at": _now_iso()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run_probe(args))


if __name__ == "__main__":
    main()
