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
MAX_MOUNTS = 128
MAX_ENVIRONMENT_NAMES = 256
MAX_SERVICES = 128
MAX_SCHEDULED_ITEMS = 128
MAX_LOCAL_FILE_BYTES = 64 * 1024
MAX_DIRECTORY_ENTRIES_SCANNED = 1024
MAX_ENVIRONMENT_NAMES_SCANNED = 1024

PROC_SELF_STATUS_PATH = Path("/proc/self/status")
SYSTEMD_SERVICE_DIRS = (
    Path("/etc/systemd/system"),
    Path("/run/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/lib/systemd/system"),
)
CRON_PATHS = (
    Path("/etc/crontab"),
    Path("/etc/cron.d"),
    Path("/etc/cron.hourly"),
    Path("/etc/cron.daily"),
    Path("/etc/cron.weekly"),
    Path("/etc/cron.monthly"),
    Path("/var/spool/cron"),
    Path("/var/spool/cron/crontabs"),
)
SENSITIVE_ENVIRONMENT_NAME_PARTS = (
    "PASSWORD",
    "PASS",
    "TOKEN",
    "SECRET",
    "KEY",
    "AUTH",
    "COOKIE",
)
LINUX_CAPABILITY_NAMES = (
    "CAP_CHOWN",
    "CAP_DAC_OVERRIDE",
    "CAP_DAC_READ_SEARCH",
    "CAP_FOWNER",
    "CAP_FSETID",
    "CAP_KILL",
    "CAP_SETGID",
    "CAP_SETUID",
    "CAP_SETPCAP",
    "CAP_LINUX_IMMUTABLE",
    "CAP_NET_BIND_SERVICE",
    "CAP_NET_BROADCAST",
    "CAP_NET_ADMIN",
    "CAP_NET_RAW",
    "CAP_IPC_LOCK",
    "CAP_IPC_OWNER",
    "CAP_SYS_MODULE",
    "CAP_SYS_RAWIO",
    "CAP_SYS_CHROOT",
    "CAP_SYS_PTRACE",
    "CAP_SYS_PACCT",
    "CAP_SYS_ADMIN",
    "CAP_SYS_BOOT",
    "CAP_SYS_NICE",
    "CAP_SYS_RESOURCE",
    "CAP_SYS_TIME",
    "CAP_SYS_TTY_CONFIG",
    "CAP_MKNOD",
    "CAP_LEASE",
    "CAP_AUDIT_WRITE",
    "CAP_AUDIT_CONTROL",
    "CAP_SETFCAP",
    "CAP_MAC_OVERRIDE",
    "CAP_MAC_ADMIN",
    "CAP_SYSLOG",
    "CAP_WAKE_ALARM",
    "CAP_BLOCK_SUSPEND",
    "CAP_AUDIT_READ",
    "CAP_PERFMON",
    "CAP_BPF",
    "CAP_CHECKPOINT_RESTORE",
)


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

            elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            elevated = None

    group_ids: list[int] = []
    if hasattr(os, "getgroups"):
        with suppress(OSError):
            group_ids = sorted(set(os.getgroups()))[:MAX_GROUPS]

    status_fields = _bounded_linux_status_fields(PROC_SELF_STATUS_PATH)[0]
    no_new_privileges_value = status_fields.get("NoNewPrivs")
    no_new_privileges = (
        no_new_privileges_value == "1" if no_new_privileges_value is not None else None
    )
    effective_capabilities = status_fields.get("CapEff")

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


def get_linux_kernel_info(_: dict[str, Any]) -> dict[str, Any]:
    """Describe the local Linux kernel without invoking uname or another command."""

    system = platform.system()
    if system != "Linux":
        return {"supported": False, "platform": system, "reason": "linux_only"}
    uname = platform.uname()
    return {
        "supported": True,
        "platform": system,
        "hostname": socket.gethostname()[:255],
        "kernel_release": _bounded_text(uname.release, 255),
        "kernel_version": _bounded_text(uname.version, 1024),
        "architecture": _bounded_text(uname.machine or platform.machine(), 255),
    }


def get_linux_identity(_: dict[str, Any]) -> dict[str, Any]:
    """Return current-process Linux identity metadata, never credential material."""

    system = platform.system()
    if system != "Linux":
        return {"supported": False, "platform": system, "reason": "linux_only"}
    group_ids, groups_truncated = _current_group_ids()
    return {
        "supported": True,
        "platform": system,
        "username": _current_user(),
        "uid": _safe_uid(),
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "gid": _safe_gid(),
        "effective_gid": os.getegid() if hasattr(os, "getegid") else None,
        "group_ids": group_ids,
        "group_names": _group_names(group_ids),
        "groups_truncated": groups_truncated,
        "credential_material_collected": False,
    }


def get_group_membership(_: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded group set already attached to the current process."""

    if not hasattr(os, "getgroups"):
        return {
            "supported": False,
            "platform": platform.system(),
            "reason": "process_group_api_unavailable",
        }
    group_ids, truncated = _current_group_ids()
    return {
        "supported": True,
        "platform": platform.system(),
        "username": _current_user(),
        "group_ids": group_ids,
        "group_names": _group_names(group_ids),
        "limit": MAX_GROUPS,
        "truncated": truncated,
    }


def get_linux_capabilities(_: dict[str, Any]) -> dict[str, Any]:
    """Read bounded capability masks for this process from the Linux procfs status file."""

    system = platform.system()
    if system != "Linux":
        return {"supported": False, "platform": system, "reason": "linux_only"}
    fields, source_truncated = _bounded_linux_status_fields(PROC_SELF_STATUS_PATH)
    if not fields:
        return {
            "supported": False,
            "platform": system,
            "reason": "proc_status_unavailable",
        }
    masks = {
        "inheritable": fields.get("CapInh"),
        "permitted": fields.get("CapPrm"),
        "effective": fields.get("CapEff"),
        "bounding": fields.get("CapBnd"),
        "ambient": fields.get("CapAmb"),
    }
    return {
        "supported": True,
        "platform": system,
        "source": str(PROC_SELF_STATUS_PATH),
        "source_truncated": source_truncated,
        "masks": masks,
        "effective_names": _capability_names(masks["effective"]),
        "permitted_names": _capability_names(masks["permitted"]),
        "bounding_names": _capability_names(masks["bounding"]),
        "ambient_names": _capability_names(masks["ambient"]),
        "no_new_privileges": _optional_flag(fields.get("NoNewPrivs")),
        "seccomp_mode": _optional_integer(fields.get("Seccomp")),
    }


def get_linux_mounts(_: dict[str, Any]) -> dict[str, Any]:
    """List bounded Linux mount metadata without reading mounted file contents."""

    system = platform.system()
    if system != "Linux":
        return {"supported": False, "platform": system, "reason": "linux_only"}
    try:
        candidates = psutil.disk_partitions(all=True)
    except (OSError, psutil.Error):
        candidates = []
    mounts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for partition in candidates:
        mountpoint = str(partition.mountpoint)[:1024]
        device = _redacted_mount_device(getattr(partition, "device", ""))
        key = (device or "", mountpoint)
        if key in seen:
            continue
        seen.add(key)
        options = str(getattr(partition, "opts", ""))
        mounts.append(
            {
                "device": device,
                "mountpoint": mountpoint,
                "filesystem": _bounded_text(getattr(partition, "fstype", ""), 64),
                "read_only": "ro" in options.split(","),
            }
        )
        if len(mounts) > MAX_MOUNTS:
            break
    return {
        "supported": True,
        "platform": system,
        "mounts": mounts[:MAX_MOUNTS],
        "limit": MAX_MOUNTS,
        "truncated": len(mounts) > MAX_MOUNTS,
        "contents_collected": False,
        "mount_options_collected": False,
    }


def get_safe_environment_overview(_: dict[str, Any]) -> dict[str, Any]:
    """List non-sensitive environment variable names without returning any values."""

    visible: list[str] = []
    filtered_count = 0
    inspected_count = 0
    total_name_count = len(os.environ)
    for name in os.environ:
        if inspected_count >= MAX_ENVIRONMENT_NAMES_SCANNED:
            break
        inspected_count += 1
        upper_name = name.upper()
        if any(part in upper_name for part in SENSITIVE_ENVIRONMENT_NAME_PARTS):
            filtered_count += 1
            continue
        if len(visible) <= MAX_ENVIRONMENT_NAMES:
            visible.append(name[:255])
    visible.sort(key=str.casefold)
    return {
        "supported": True,
        "names": visible[:MAX_ENVIRONMENT_NAMES],
        "limit": MAX_ENVIRONMENT_NAMES,
        "truncated": (len(visible) > MAX_ENVIRONMENT_NAMES or inspected_count < total_name_count),
        "inspected_count": inspected_count,
        "total_name_count": total_name_count,
        "filtered_count": filtered_count,
        "values_collected": False,
        "filtered_names_collected": False,
    }


def get_service_overview(_: dict[str, Any]) -> dict[str, Any]:
    """Return bounded service names and state where a local API makes it available."""

    system = platform.system()
    if system == "Windows":
        return _windows_service_overview()
    if system == "Linux":
        entries, sources, truncated = _fixed_directory_entries(
            SYSTEMD_SERVICE_DIRS,
            limit=MAX_SERVICES,
            suffixes=(".service",),
            kind="systemd_unit",
        )
        return {
            "supported": bool(sources),
            "platform": system,
            "manager": "systemd_unit_files" if sources else None,
            "services": entries,
            "sources": sources,
            "limit": MAX_SERVICES,
            "truncated": truncated,
            "status_available": False,
            "unit_contents_collected": False,
        }
    return {"supported": False, "platform": system, "reason": "service_api_unavailable"}


def get_scheduled_activity_overview(_: dict[str, Any]) -> dict[str, Any]:
    """Describe fixed local scheduler locations without reading task definitions."""

    system = platform.system()
    if system != "Linux":
        return {"supported": False, "platform": system, "reason": "linux_only"}

    cron_entries, cron_sources, cron_truncated = _fixed_schedule_entries(
        CRON_PATHS, MAX_SCHEDULED_ITEMS
    )
    remaining = max(0, MAX_SCHEDULED_ITEMS - len(cron_entries))
    timer_entries: list[dict[str, Any]] = []
    timer_sources: list[str] = []
    timer_truncated = False
    if remaining:
        timer_entries, timer_sources, timer_truncated = _fixed_directory_entries(
            SYSTEMD_SERVICE_DIRS,
            limit=remaining,
            suffixes=(".timer",),
            kind="systemd_timer",
        )
    elif any(path.is_dir() for path in SYSTEMD_SERVICE_DIRS):
        timer_truncated = True
    entries = cron_entries + timer_entries
    sources = sorted(set(cron_sources + timer_sources))
    return {
        "supported": bool(sources),
        "platform": system,
        "activities": entries,
        "sources": sources,
        "limit": MAX_SCHEDULED_ITEMS,
        "truncated": cron_truncated or timer_truncated,
        "definitions_collected": False,
        "commands_collected": False,
    }


def get_privilege_enumeration(_: dict[str, Any]) -> dict[str, Any]:
    """Summarize the current process privilege boundary without attempting escalation."""

    identity = (
        get_linux_identity({})
        if platform.system() == "Linux"
        else {"supported": True, **get_security_context({})}
    )
    return {
        "supported": True,
        "platform": platform.system(),
        "scope": "current_process_and_user",
        "identity": identity,
        "groups": get_group_membership({}),
        "capabilities": get_linux_capabilities({}),
        "privilege_escalation_attempted": False,
        "credential_material_collected": False,
        "policy_files_read": False,
    }


def get_network_overview(_: dict[str, Any]) -> dict[str, Any]:
    """Aggregate passive local network state with fixed collection limits."""

    return {
        "supported": True,
        "scope": "local_host_only",
        "active_network_probing": False,
        "dns_resolution_performed": False,
        "interfaces": get_network_interfaces({}),
        "routes": get_route_table({}),
        "listening_ports": get_listening_ports({"limit": 100}),
        "connections": get_network_connections({"limit": 100}),
    }


def get_host_recon(_: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded passive overview suitable for a controlled lab host."""

    return {
        "supported": True,
        "scope": "local_host_only",
        "active_network_probing": False,
        "credential_material_collected": False,
        "arbitrary_paths_accepted": False,
        "system": get_system_info({}),
        "kernel": get_linux_kernel_info({}),
        "uptime": get_uptime({}),
        "privileges": get_privilege_enumeration({}),
        "network": get_network_overview({}),
        "mounts": get_linux_mounts({}),
        "services": get_service_overview({}),
        "scheduled_activity": get_scheduled_activity_overview({}),
        "environment": get_safe_environment_overview({}),
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


def _bounded_linux_status_fields(path: Path) -> tuple[dict[str, str], bool]:
    wanted = {
        "CapInh",
        "CapPrm",
        "CapEff",
        "CapBnd",
        "CapAmb",
        "NoNewPrivs",
        "Seccomp",
    }
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_LOCAL_FILE_BYTES + 1)
    except OSError:
        return {}, False
    truncated = len(raw) > MAX_LOCAL_FILE_BYTES
    fields: dict[str, str] = {}
    for line in raw[:MAX_LOCAL_FILE_BYTES].decode("utf-8", errors="replace").splitlines():
        key, separator, value = line.partition(":")
        if separator and key in wanted:
            fields[key] = value.strip()[:64]
    return fields, truncated


def _current_group_ids() -> tuple[list[int], bool]:
    if not hasattr(os, "getgroups"):
        return [], False
    try:
        raw_group_ids = sorted(set(os.getgroups()))
    except OSError:
        return [], False
    return raw_group_ids[:MAX_GROUPS], len(raw_group_ids) > MAX_GROUPS


def _capability_names(mask: str | None) -> list[str]:
    if mask is None:
        return []
    try:
        value = int(mask, 16)
    except ValueError:
        return []
    return [name for bit, name in enumerate(LINUX_CAPABILITY_NAMES) if value & (1 << bit)]


def _optional_flag(value: str | None) -> bool | None:
    if value == "0":
        return False
    if value == "1":
        return True
    return None


def _optional_integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _redacted_mount_device(value: object) -> str | None:
    device = str(value)[:512]
    if not device:
        return None
    scheme_index = device.find("://")
    if scheme_index >= 0:
        authority_start = scheme_index + 3
        at_index = device.find("@", authority_start)
        if at_index >= authority_start:
            return f"{device[:authority_start]}[redacted]{device[at_index:]}"
    if device.startswith("//"):
        at_index = device.find("@", 2)
        if at_index >= 2:
            return f"//[redacted]{device[at_index:]}"
    return device


def _windows_service_overview() -> dict[str, Any]:
    iterator_factory = getattr(psutil, "win_service_iter", None)
    if not callable(iterator_factory):
        return {
            "supported": False,
            "platform": "Windows",
            "reason": "windows_service_api_unavailable",
        }
    services: list[dict[str, Any]] = []
    try:
        iterator = iterator_factory()
        for service in iterator:
            try:
                info = service.as_dict()
            except (OSError, psutil.Error):
                continue
            services.append(
                {
                    "name": _bounded_text(info.get("name"), 255),
                    "display_name": _bounded_text(info.get("display_name"), 255),
                    "status": _bounded_text(info.get("status"), 64),
                    "start_type": _bounded_text(info.get("start_type"), 64),
                }
            )
            if len(services) > MAX_SERVICES:
                break
    except (OSError, psutil.Error):
        return {
            "supported": False,
            "platform": "Windows",
            "reason": "windows_service_query_failed",
        }
    services.sort(key=lambda item: (item["name"] or "").casefold())
    return {
        "supported": True,
        "platform": "Windows",
        "manager": "windows_service_api",
        "services": services[:MAX_SERVICES],
        "limit": MAX_SERVICES,
        "truncated": len(services) > MAX_SERVICES,
        "status_available": True,
        "service_commands_collected": False,
    }


def _fixed_directory_entries(
    roots: Iterable[Path],
    *,
    limit: int,
    suffixes: tuple[str, ...] | None,
    kind: str,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    entries: list[dict[str, Any]] = []
    sources: list[str] = []
    seen_names: set[str] = set()
    scanned = 0
    truncated = False
    for root in roots:
        if len(entries) > limit or scanned >= MAX_DIRECTORY_ENTRIES_SCANNED:
            truncated = True
            break
        try:
            if not root.is_dir():
                continue
            iterator = os.scandir(root)
        except OSError:
            continue
        sources.append(str(root))
        with iterator:
            for entry in iterator:
                if scanned >= MAX_DIRECTORY_ENTRIES_SCANNED:
                    truncated = True
                    break
                scanned += 1
                name = entry.name[:255]
                if suffixes is not None and not name.casefold().endswith(suffixes):
                    continue
                if name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    is_symlink: bool | None = entry.is_symlink()
                except OSError:
                    is_symlink = None
                entries.append(
                    {
                        "name": name,
                        "kind": kind,
                        "source": str(root),
                        "is_symlink": is_symlink,
                    }
                )
                if len(entries) > limit:
                    truncated = True
                    break
    entries.sort(key=lambda item: str(item["name"]).casefold())
    return entries[:limit], sources, truncated


def _fixed_schedule_entries(
    paths: Iterable[Path], limit: int
) -> tuple[list[dict[str, Any]], list[str], bool]:
    entries: list[dict[str, Any]] = []
    sources: list[str] = []
    directory_paths: list[Path] = []
    for path in paths:
        try:
            if path.is_file():
                sources.append(str(path))
                entries.append(
                    {
                        "name": path.name[:255],
                        "kind": "cron_file",
                        "source": str(path.parent),
                        "is_symlink": path.is_symlink(),
                    }
                )
            elif path.is_dir():
                directory_paths.append(path)
        except OSError:
            continue
        if len(entries) > limit:
            return entries[:limit], sources, True

    remaining = max(0, limit - len(entries))
    if remaining == 0:
        return entries[:limit], sources, bool(directory_paths)
    directory_entries, directory_sources, truncated = _fixed_directory_entries(
        directory_paths,
        limit=remaining,
        suffixes=None,
        kind="cron_entry",
    )
    entries.extend(directory_entries)
    sources.extend(directory_sources)
    entries.sort(key=lambda item: (str(item["kind"]), str(item["name"]).casefold()))
    return entries[:limit], sources, truncated


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
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for registry_path in paths:
            try:
                root = winreg.OpenKey(hive, registry_path)
            except OSError:
                continue
            with root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                        subkey = winreg.OpenKey(root, subkey_name)
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
