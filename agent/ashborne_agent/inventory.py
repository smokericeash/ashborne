"""Bounded, read-only host observations used by explicitly allowlisted tasks.

This module deliberately has no subprocess or shell integration. Inventory is
collected through Python and psutil APIs, and large collections are capped.
"""

from __future__ import annotations

import getpass
import importlib.metadata
import ipaddress
import os
import platform
import socket
import stat
import tempfile
import time
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from ashborne_agent import __version__

MAX_INTERFACES = 64
MAX_ADDRESSES_PER_INTERFACE = 16
MAX_DISKS = 64
MAX_PROCESSES = 500
MAX_SOFTWARE = 500
MAX_PORTS = 500
MAX_CONNECTIONS = 500
MAX_ROUTES = 256
MAX_GROUPS = 64


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def primary_ip_address() -> str | None:
    """Return a non-loopback address without contacting an external service."""
    try:
        addresses = psutil.net_if_addrs()
    except (OSError, psutil.Error):
        return None
    fallbacks: list[str] = []
    for values in addresses.values():
        for address in values:
            if address.family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            value = address.address.split("%", 1)[0]
            if value in {"127.0.0.1", "::1"}:
                continue
            if address.family == socket.AF_INET:
                return value
            fallbacks.append(value)
    return fallbacks[0] if fallbacks else None


def get_system_info(_: dict[str, Any]) -> dict[str, Any]:
    uname = platform.uname()
    return {
        "hostname": socket.gethostname(),
        "username": _current_user(),
        "operating_system": uname.system,
        "os_version": platform.platform(aliased=True, terse=False),
        "kernel_release": uname.release,
        "kernel_version": uname.version,
        "architecture": uname.machine or platform.machine(),
        "processor": uname.processor or platform.processor() or None,
        "python_version": platform.python_version(),
        "agent_version": __version__,
        "ip_address": primary_ip_address(),
    }


def get_quick_recon(_: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded local-host baseline without active network probing."""

    interfaces = get_network_interfaces({})
    listeners = get_listening_ports({"limit": 100})
    routes = get_route_table({})
    return {
        "scope": "local_host_only",
        "active_network_probing": False,
        "system": get_system_info({}),
        "security_context": get_security_context({}),
        "uptime": get_uptime({}),
        "network": {
            "interfaces": interfaces["interfaces"],
            "interfaces_truncated": interfaces["truncated"],
            "listening_ports": listeners["listeners"],
            "listeners_truncated": listeners["truncated"],
            "routes": routes["routes"],
            "routes_supported": routes["supported"],
            "routes_truncated": routes["truncated"],
        },
        "file_system": get_file_system_overview({}),
    }


def get_hostname(_: dict[str, Any]) -> dict[str, str]:
    return {"hostname": socket.gethostname()}


def get_current_user(_: dict[str, Any]) -> dict[str, Any]:
    return {"username": _current_user(), "uid": _safe_uid(), "gid": _safe_gid()}


def get_security_context(_: dict[str, Any]) -> dict[str, Any]:
    uid = _safe_uid()
    gid = _safe_gid()
    effective_uid = os.geteuid() if hasattr(os, "geteuid") else uid
    effective_gid = os.getegid() if hasattr(os, "getegid") else gid
    elevated: bool | None = effective_uid == 0 if effective_uid is not None else None
    if os.name == "nt":
        try:
            import ctypes

            elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            elevated = None

    group_ids: list[int] = []
    if hasattr(os, "getgroups"):
        with suppress(OSError):
            group_ids = sorted(set(os.getgroups()))[:MAX_GROUPS]

    no_new_privileges: bool | None = None
    effective_capabilities: str | None = None
    status_path = Path("/proc/self/status")
    if status_path.is_file():
        try:
            for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("NoNewPrivs:"):
                    no_new_privileges = line.partition(":")[2].strip() == "1"
                elif line.startswith("CapEff:"):
                    effective_capabilities = line.partition(":")[2].strip()[:32]
        except OSError:
            pass

    return {
        "username": _current_user(),
        "uid": uid,
        "effective_uid": effective_uid,
        "gid": gid,
        "effective_gid": effective_gid,
        "group_ids": group_ids,
        "group_names": _group_names(group_ids),
        "is_elevated": elevated,
        "no_new_privileges": no_new_privileges,
        "effective_capabilities_mask": effective_capabilities,
    }


def get_cpu_info(_: dict[str, Any]) -> dict[str, Any]:
    frequency = None
    try:
        raw_frequency = psutil.cpu_freq()
        if raw_frequency:
            frequency = {
                "current_mhz": round(raw_frequency.current, 2),
                "minimum_mhz": round(raw_frequency.min, 2),
                "maximum_mhz": round(raw_frequency.max, 2),
            }
    except (OSError, psutil.Error):
        pass
    load_average = None
    try:
        one, five, fifteen = psutil.getloadavg()
        load_average = {"one_minute": one, "five_minutes": five, "fifteen_minutes": fifteen}
    except (AttributeError, OSError, psutil.Error):
        pass
    return {
        "architecture": platform.machine(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent": psutil.cpu_percent(interval=None),
        "frequency": frequency,
        "load_average": load_average,
    }


def get_memory_usage(_: dict[str, Any]) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "physical": _usage_dict(memory, include_percent=True),
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "free_bytes": swap.free,
            "percent": swap.percent,
        },
    }


def get_disk_usage(parameters: dict[str, Any]) -> dict[str, Any]:
    include_all = parameters.get("all_partitions", False)
    partitions: list[dict[str, Any]] = []
    seen_mountpoints: set[str] = set()
    try:
        candidates: list[Any] = list(psutil.disk_partitions(all=include_all))
    except (OSError, psutil.Error):
        candidates = []

    # Containers sometimes omit the root filesystem from disk_partitions().
    root = Path.cwd().anchor or os.sep
    if root not in {candidate.mountpoint for candidate in candidates}:
        candidates.insert(0, _SyntheticPartition(root))

    for partition in candidates:
        mountpoint = str(partition.mountpoint)
        if mountpoint in seen_mountpoints:
            continue
        seen_mountpoints.add(mountpoint)
        try:
            usage = psutil.disk_usage(mountpoint)
        except (OSError, PermissionError, psutil.Error):
            continue
        partitions.append(
            {
                "device": str(getattr(partition, "device", ""))[:512] or None,
                "mountpoint": mountpoint[:1024],
                "filesystem": str(getattr(partition, "fstype", ""))[:64] or None,
                **_usage_dict(usage, include_percent=True),
            }
        )
        if len(partitions) >= MAX_DISKS:
            break
    return {"partitions": partitions, "truncated": len(seen_mountpoints) > len(partitions)}


def get_file_system_overview(_: dict[str, Any]) -> dict[str, Any]:
    """Describe fixed local locations without reading file contents or accepting paths."""

    root = Path.cwd().anchor or os.sep
    locations = {
        "working_directory": Path.cwd(),
        "home_directory": Path.home(),
        "temporary_directory": Path(tempfile.gettempdir()),
        "root_directory": Path(root),
    }
    return {
        "scope": "fixed_locations_only",
        "contents_collected": False,
        "locations": {name: _path_metadata(path) for name, path in locations.items()},
        "volumes": get_disk_usage({"all_partitions": False})["partitions"],
    }


def get_network_interfaces(_: dict[str, Any]) -> dict[str, Any]:
    try:
        address_map = psutil.net_if_addrs()
    except (OSError, psutil.Error):
        address_map = {}
    try:
        stat_map = psutil.net_if_stats()
    except (OSError, psutil.Error):
        stat_map = {}

    interfaces: list[dict[str, Any]] = []
    for name in sorted(address_map)[:MAX_INTERFACES]:
        addresses: list[dict[str, Any]] = []
        for address in address_map[name][:MAX_ADDRESSES_PER_INTERFACE]:
            addresses.append(
                {
                    "family": _address_family_name(address.family),
                    "address": str(address.address)[:512],
                    "netmask": str(address.netmask)[:512] if address.netmask else None,
                    "broadcast": str(address.broadcast)[:512] if address.broadcast else None,
                }
            )
        stats = stat_map.get(name)
        interfaces.append(
            {
                "name": name[:255],
                "is_up": stats.isup if stats else None,
                "speed_mbps": stats.speed if stats and stats.speed >= 0 else None,
                "mtu": stats.mtu if stats else None,
                "addresses": addresses,
                "addresses_truncated": len(address_map[name]) > len(addresses),
            }
        )
    return {
        "interfaces": interfaces,
        "truncated": len(address_map) > len(interfaces),
        "primary_ip_address": primary_ip_address(),
    }


def get_network_connections(parameters: dict[str, Any]) -> dict[str, Any]:
    limit = parameters.get("limit", 200)
    connections: list[dict[str, Any]] = []
    try:
        candidates = psutil.net_connections(kind="inet")
    except (OSError, psutil.AccessDenied, psutil.Error):
        candidates = []
    for connection in candidates:
        pid = connection.pid
        process_name = None
        if pid is not None:
            with suppress(psutil.Error, OSError):
                process_name = _bounded_text(psutil.Process(pid).name(), 255)
        connections.append(
            {
                "transport": "tcp" if connection.type == socket.SOCK_STREAM else "udp",
                "family": _address_family_name(connection.family),
                "status": _bounded_text(connection.status, 32),
                "local": _endpoint(connection.laddr),
                "remote": _endpoint(connection.raddr),
                "pid": pid,
                "process_name": process_name,
            }
        )
    connections.sort(
        key=lambda value: (
            value["transport"],
            str(value["local"]),
            str(value["remote"]),
            value["pid"] if value["pid"] is not None else -1,
        )
    )
    return {
        "connections": connections[:limit],
        "limit": limit,
        "truncated": len(connections) > limit,
        "dns_resolution_performed": False,
    }


def get_route_table(_: dict[str, Any]) -> dict[str, Any]:
    """Read the local Linux route table without starting an OS command."""

    routes: list[dict[str, Any]] = []
    source_files: list[str] = []
    collection_limit = MAX_ROUTES + 1
    ipv4_path = Path("/proc/net/route")
    if ipv4_path.is_file():
        source_files.append(str(ipv4_path))
        routes.extend(_linux_ipv4_routes(ipv4_path, collection_limit))
    remaining = max(0, collection_limit - len(routes))
    ipv6_path = Path("/proc/net/ipv6_route")
    if remaining and ipv6_path.is_file():
        source_files.append(str(ipv6_path))
        routes.extend(_linux_ipv6_routes(ipv6_path, remaining))
    return {
        "routes": routes[:MAX_ROUTES],
        "supported": bool(source_files),
        "source": source_files or None,
        "truncated": len(routes) > MAX_ROUTES,
    }


def get_uptime(_: dict[str, Any]) -> dict[str, Any]:
    boot_time = psutil.boot_time()
    return {
        "boot_time": datetime.fromtimestamp(boot_time, UTC).isoformat(),
        "uptime_seconds": max(0, int(time.time() - boot_time)),
    }


def get_process_inventory(parameters: dict[str, Any]) -> dict[str, Any]:
    limit = parameters.get("limit", 200)
    processes: list[dict[str, Any]] = []
    attributes = ["pid", "name", "username", "status", "create_time", "memory_percent"]
    try:
        iterator = psutil.process_iter(attrs=attributes, ad_value=None)
        for process in iterator:
            info = process.info
            create_time = info.get("create_time")
            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": _bounded_text(info.get("name"), 255),
                    "username": _bounded_text(info.get("username"), 255),
                    "status": _bounded_text(info.get("status"), 64),
                    "created_at": (
                        datetime.fromtimestamp(create_time, UTC).isoformat()
                        if isinstance(create_time, (int, float))
                        else None
                    ),
                    "memory_percent": _rounded(info.get("memory_percent")),
                }
            )
            if len(processes) >= limit:
                break
    except (OSError, psutil.Error):
        pass
    processes.sort(key=lambda value: value.get("pid") or -1)
    return {"processes": processes, "limit": limit, "truncated": len(processes) >= limit}


def get_installed_software(parameters: dict[str, Any]) -> dict[str, Any]:
    limit = parameters.get("limit", 300)
    items: dict[tuple[str, str], dict[str, str | None]] = {}
    for item in _platform_software(limit):
        name = item.get("name")
        if not name:
            continue
        key = (name.casefold(), (item.get("version") or "").casefold())
        items.setdefault(key, item)
        if len(items) >= limit:
            break
    if len(items) < limit:
        for distribution in importlib.metadata.distributions():
            name = _bounded_text(distribution.metadata.get("Name"), 255)
            if not name:
                continue
            version = _bounded_text(distribution.version, 128)
            key = (name.casefold(), (version or "").casefold())
            items.setdefault(key, {"name": name, "version": version, "source": "python"})
            if len(items) >= limit:
                break
    software = sorted(
        items.values(),
        key=lambda item: ((item.get("name") or "").casefold(), item.get("version") or ""),
    )
    return {"software": software[:limit], "limit": limit, "truncated": len(software) >= limit}


def get_listening_ports(parameters: dict[str, Any]) -> dict[str, Any]:
    limit = parameters.get("limit", 300)
    listeners: list[dict[str, Any]] = []
    try:
        connections = psutil.net_connections(kind="inet")
    except (OSError, psutil.AccessDenied, psutil.Error):
        connections = []
    for connection in connections:
        if connection.type == socket.SOCK_STREAM and connection.status != psutil.CONN_LISTEN:
            continue
        if connection.type == socket.SOCK_DGRAM and connection.status not in {
            psutil.CONN_NONE,
            "NONE",
        }:
            continue
        local = connection.laddr
        if not local:
            continue
        pid = connection.pid
        process_name = None
        if pid is not None:
            with suppress(psutil.Error, OSError):
                process_name = _bounded_text(psutil.Process(pid).name(), 255)
        listeners.append(
            {
                "transport": "tcp" if connection.type == socket.SOCK_STREAM else "udp",
                "family": _address_family_name(connection.family),
                "local_address": _bounded_text(getattr(local, "ip", local[0]), 255),
                "local_port": int(getattr(local, "port", local[1])),
                "pid": pid,
                "process_name": process_name,
            }
        )
    listeners.sort(
        key=lambda value: (
            value["local_port"],
            value["transport"],
            value["local_address"] or "",
        )
    )
    return {"listeners": listeners[:limit], "limit": limit, "truncated": len(listeners) > limit}


def get_agent_health(_: dict[str, Any]) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    root = Path.cwd().anchor or os.sep
    try:
        disk = psutil.disk_usage(root)
        disk_percent: float | None = disk.percent
    except (OSError, psutil.Error):
        disk_percent = None
    return {
        "status": "healthy",
        "agent_version": __version__,
        "process_id": os.getpid(),
        "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": memory.percent,
        "disk_percent": disk_percent,
        "collected_at": utc_now(),
    }


def ping(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "pong": True,
        "message": parameters.get("message"),
        "received_at": utc_now(),
    }


def _platform_software(limit: int) -> Iterable[dict[str, str | None]]:
    system = platform.system()
    if system == "Windows":
        yield from _windows_software(limit)
    elif Path("/var/lib/dpkg/status").is_file():
        yield from _debian_software(limit)
    elif Path("/lib/apk/db/installed").is_file():
        yield from _alpine_software(limit)
    elif system == "Darwin":
        yield from _macos_apps(limit)


def _debian_software(limit: int) -> Iterable[dict[str, str | None]]:
    name: str | None = None
    version: str | None = None
    status: str | None = None
    yielded = 0
    try:
        with Path("/var/lib/dpkg/status").open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line == "\n":
                    if name and status == "install ok installed":
                        yield {"name": name, "version": version, "source": "dpkg"}
                        yielded += 1
                        if yielded >= limit:
                            return
                    name = version = status = None
                elif line.startswith("Package: "):
                    name = _bounded_text(line[9:].strip(), 255)
                elif line.startswith("Version: "):
                    version = _bounded_text(line[9:].strip(), 128)
                elif line.startswith("Status: "):
                    status = line[8:].strip()
    except (OSError, UnicodeError):
        return


def _alpine_software(limit: int) -> Iterable[dict[str, str | None]]:
    name: str | None = None
    version: str | None = None
    yielded = 0
    try:
        with Path("/lib/apk/db/installed").open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line == "\n":
                    if name:
                        yield {"name": name, "version": version, "source": "apk"}
                        yielded += 1
                        if yielded >= limit:
                            return
                    name = version = None
                elif line.startswith("P:"):
                    name = _bounded_text(line[2:].strip(), 255)
                elif line.startswith("V:"):
                    version = _bounded_text(line[2:].strip(), 128)
    except (OSError, UnicodeError):
        return


def _windows_software(limit: int) -> Iterable[dict[str, str | None]]:
    try:
        import winreg
    except ImportError:
        return
    paths = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    yielded = 0
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):  # type: ignore[attr-defined]
        for registry_path in paths:
            try:
                root = winreg.OpenKey(hive, registry_path)  # type: ignore[attr-defined]
            except OSError:
                continue
            with root:
                for index in range(winreg.QueryInfoKey(root)[0]):  # type: ignore[attr-defined]
                    try:
                        subkey_name = winreg.EnumKey(root, index)  # type: ignore[attr-defined]
                        subkey = winreg.OpenKey(root, subkey_name)  # type: ignore[attr-defined]
                        with subkey:
                            name = _registry_value(winreg, subkey, "DisplayName")
                            version = _registry_value(winreg, subkey, "DisplayVersion")
                    except OSError:
                        continue
                    if name:
                        yield {
                            "name": _bounded_text(name, 255),
                            "version": _bounded_text(version, 128),
                            "source": "windows_registry",
                        }
                        yielded += 1
                        if yielded >= limit:
                            return


def _registry_value(winreg: Any, key: Any, name: str) -> str | None:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if isinstance(value, str) else None


def _macos_apps(limit: int) -> Iterable[dict[str, str | None]]:
    yielded = 0
    for root in (Path("/Applications"), Path.home() / "Applications"):
        try:
            children = sorted(root.iterdir(), key=lambda item: item.name.casefold())
        except (OSError, PermissionError):
            continue
        for child in children:
            if child.suffix.casefold() != ".app":
                continue
            yield {"name": child.stem[:255], "version": None, "source": "applications"}
            yielded += 1
            if yielded >= limit:
                return


def _usage_dict(value: Any, *, include_percent: bool) -> dict[str, Any]:
    result = {
        "total_bytes": value.total,
        "used_bytes": value.used,
        "available_bytes": getattr(value, "available", getattr(value, "free", None)),
        "free_bytes": getattr(value, "free", None),
    }
    if include_percent:
        result["percent"] = value.percent
    return result


def _current_user() -> str:
    try:
        return getpass.getuser()[:255]
    except (OSError, KeyError):
        return "unknown"


def _safe_uid() -> int | None:
    return os.getuid() if hasattr(os, "getuid") else None


def _safe_gid() -> int | None:
    return os.getgid() if hasattr(os, "getgid") else None


def _address_family_name(value: object) -> str:
    names = {
        socket.AF_INET: "IPv4",
        socket.AF_INET6: "IPv6",
        getattr(psutil, "AF_LINK", object()): "MAC",
    }
    return names.get(value, str(value))


def _endpoint(value: object) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        address = getattr(value, "ip", value[0])  # type: ignore[index]
        port = getattr(value, "port", value[1])  # type: ignore[index]
    except (IndexError, TypeError):
        return None
    if port is None:
        return None
    return {"address": _bounded_text(address, 255), "port": int(port)}


def _path_metadata(path: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    result: dict[str, Any] = {
        "path": str(resolved)[:1024],
        "exists": path.exists(),
        "is_directory": path.is_dir(),
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
        "executable": os.access(path, os.X_OK),
    }
    try:
        metadata = path.stat()
        result.update(
            {
                "mode": oct(stat.S_IMODE(metadata.st_mode)),
                "owner_uid": getattr(metadata, "st_uid", None),
                "owner_gid": getattr(metadata, "st_gid", None),
            }
        )
    except (OSError, PermissionError):
        result.update({"mode": None, "owner_uid": None, "owner_gid": None})
    return result


def _group_names(group_ids: list[int]) -> list[str]:
    if not group_ids or os.name == "nt":
        return []
    try:
        group_module = importlib.import_module("grp")
    except ImportError:
        return []
    lookup_group = getattr(group_module, "getgrgid", None)
    if not callable(lookup_group):
        return []
    names: list[str] = []
    for group_id in group_ids[:MAX_GROUPS]:
        with suppress(KeyError):
            names.append(str(lookup_group(group_id).gr_name)[:255])
    return names


def _linux_ipv4_routes(path: Path, limit: int) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    try:
        with path.open(encoding="ascii", errors="replace") as stream:
            next(stream, None)
            for line in stream:
                fields = line.split()
                if len(fields) < 8:
                    continue
                try:
                    destination = socket.inet_ntoa(bytes.fromhex(fields[1])[::-1])
                    gateway = socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
                    mask = socket.inet_ntoa(bytes.fromhex(fields[7])[::-1])
                    network = ipaddress.IPv4Network((destination, mask), strict=False)
                    metric = int(fields[6])
                except (OSError, ValueError):
                    continue
                routes.append(
                    {
                        "family": "IPv4",
                        "interface": fields[0][:255],
                        "destination": str(network),
                        "gateway": None if gateway == "0.0.0.0" else gateway,
                        "metric": metric,
                    }
                )
                if len(routes) >= limit:
                    break
    except OSError:
        return []
    return routes


def _linux_ipv6_routes(path: Path, limit: int) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    try:
        with path.open(encoding="ascii", errors="replace") as stream:
            for line in stream:
                fields = line.split()
                if len(fields) < 10:
                    continue
                try:
                    prefix = int(fields[1], 16)
                    destination = ipaddress.IPv6Address(int(fields[0], 16))
                    network = ipaddress.IPv6Network((destination, prefix), strict=False)
                    gateway_address = ipaddress.IPv6Address(int(fields[4], 16))
                    metric = int(fields[5], 16)
                except ValueError:
                    continue
                routes.append(
                    {
                        "family": "IPv6",
                        "interface": fields[-1][:255],
                        "destination": str(network),
                        "gateway": None if gateway_address.is_unspecified else str(gateway_address),
                        "metric": metric,
                    }
                )
                if len(routes) >= limit:
                    break
    except OSError:
        return []
    return routes


def _bounded_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _rounded(value: object) -> float | None:
    return round(float(value), 4) if isinstance(value, (int, float)) else None


class _SyntheticPartition:
    def __init__(self, mountpoint: str) -> None:
        self.device = ""
        self.mountpoint = mountpoint
        self.fstype = ""
