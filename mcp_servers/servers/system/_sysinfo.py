from __future__ import annotations

import time
from typing import Any

import psutil

from mcp_servers.servers.system._shell import fail, ok


def battery_status() -> dict[str, Any]:
    """Report battery charge percentage, charging state, and time remaining."""
    battery = psutil.sensors_battery()
    if battery is None:
        return fail("no_battery", "This machine has no battery (desktop or battery sensor unavailable).")

    time_remaining = None
    if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        time_remaining = f"{battery.secsleft // 3600}h {(battery.secsleft % 3600) // 60}m"

    return ok(
        {
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "time_remaining": time_remaining,
        }
    )


def cpu_usage() -> dict[str, Any]:
    """Report current CPU utilization percentage and core count."""
    percent = psutil.cpu_percent(interval=0.5)
    return ok({"percent": percent, "core_count": psutil.cpu_count()})


def memory_usage() -> dict[str, Any]:
    """Report current memory usage: total, used, available, and percent."""
    vm = psutil.virtual_memory()
    gib = 1024**3
    return ok(
        {
            "total_gb": round(vm.total / gib, 2),
            "used_gb": round(vm.used / gib, 2),
            "available_gb": round(vm.available / gib, 2),
            "percent": vm.percent,
        }
    )


def disk_usage(path: str = "/") -> dict[str, Any]:
    """Report disk usage for the given mount point (defaults to the root volume)."""
    try:
        disk = psutil.disk_usage(path)
    except FileNotFoundError:
        return fail("path_not_found", f"No such path or mount point: {path!r}")

    gib = 1024**3
    return ok(
        {
            "path": path,
            "total_gb": round(disk.total / gib, 2),
            "used_gb": round(disk.used / gib, 2),
            "free_gb": round(disk.free / gib, 2),
            "percent": disk.percent,
        }
    )


def uptime() -> dict[str, Any]:
    """Report how long the machine has been running since last boot."""
    seconds = time.time() - psutil.boot_time()
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")

    return ok({"uptime": " ".join(parts), "seconds": int(seconds)})
