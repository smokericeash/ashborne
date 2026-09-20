from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ashborne_agent import inventory
from ashborne_agent.executor import TaskValidationError, validate_task

NEW_ENUMERATION_TASKS = (
    "LINUX_KERNEL_INFO",
    "LINUX_IDENTITY",
    "GROUP_MEMBERSHIP",
    "LINUX_CAPABILITIES",
    "LINUX_MOUNTS",
    "SAFE_ENVIRONMENT_OVERVIEW",
    "SERVICE_OVERVIEW",
    "SCHEDULED_ACTIVITY_OVERVIEW",
    "PRIVILEGE_ENUMERATION",
    "NETWORK_OVERVIEW",
    "HOST_RECON",
)


@pytest.mark.parametrize("task_type", NEW_ENUMERATION_TASKS)
def test_new_enumeration_tasks_reject_all_parameters(task_type: str) -> None:
    assert validate_task(task_type, {}) == {}
    with pytest.raises(TaskValidationError, match="unsupported parameter"):
        validate_task(task_type, {"path": "/tmp"})


def test_linux_kernel_info_is_local_platform_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        inventory.platform,
        "uname",
        lambda: SimpleNamespace(
            release="6.9-lab",
            version="lab kernel",
            machine="x86_64",
        ),
    )
    result = inventory.get_linux_kernel_info({})
    assert result == {
        "supported": True,
        "platform": "Linux",
        "hostname": result["hostname"],
        "kernel_release": "6.9-lab",
        "kernel_version": "lab kernel",
        "architecture": "x86_64",
    }


@pytest.mark.parametrize(
    "collector",
    [
        inventory.get_linux_kernel_info,
        inventory.get_linux_identity,
        inventory.get_linux_capabilities,
        inventory.get_linux_mounts,
        inventory.get_scheduled_activity_overview,
    ],
)
def test_linux_only_actions_report_unsupported_platform(
    collector: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inventory.platform, "system", lambda: "Windows")
    assert collector({}) == {
        "supported": False,
        "platform": "Windows",
        "reason": "linux_only",
    }


def test_linux_identity_and_group_membership_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        inventory.os,
        "getgroups",
        lambda: list(range(inventory.MAX_GROUPS + 10)),
        raising=False,
    )
    monkeypatch.setattr(inventory.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(inventory.os, "geteuid", lambda: 1001, raising=False)
    monkeypatch.setattr(inventory.os, "getgid", lambda: 2000, raising=False)
    monkeypatch.setattr(inventory.os, "getegid", lambda: 2001, raising=False)

    identity = inventory.get_linux_identity({})
    groups = inventory.get_group_membership({})

    assert identity["uid"] == 1000
    assert identity["effective_uid"] == 1001
    assert identity["gid"] == 2000
    assert identity["effective_gid"] == 2001
    assert identity["credential_material_collected"] is False
    assert len(identity["group_ids"]) == inventory.MAX_GROUPS
    assert identity["groups_truncated"] is True
    assert len(groups["group_ids"]) == inventory.MAX_GROUPS
    assert groups["truncated"] is True


def test_linux_capabilities_use_a_bounded_proc_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_path = tmp_path / "status"
    status_path.write_bytes(
        b"CapInh:\t0000000000000000\n"
        b"CapPrm:\t0000000000002400\n"
        b"CapEff:\t0000000000002400\n"
        b"CapBnd:\t000001ffffffffff\n"
        b"CapAmb:\t0000000000000000\n"
        b"NoNewPrivs:\t1\n"
        b"Seccomp:\t2\n" + b"X" * (inventory.MAX_LOCAL_FILE_BYTES + 32)
    )
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory, "PROC_SELF_STATUS_PATH", status_path)

    result = inventory.get_linux_capabilities({})

    assert result["supported"] is True
    assert result["source_truncated"] is True
    assert result["no_new_privileges"] is True
    assert result["seccomp_mode"] == 2
    assert result["effective_names"] == ["CAP_NET_BIND_SERVICE", "CAP_NET_RAW"]
    assert result["masks"]["effective"] == "0000000000002400"


def test_linux_mounts_are_bounded_and_redact_embedded_userinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        SimpleNamespace(
            device="nfs://lab-user:lab-password@server/share",
            mountpoint=f"/mnt/{index}",
            fstype="nfs",
            opts="ro,nosuid",
        )
        for index in range(inventory.MAX_MOUNTS + 5)
    ]
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory.psutil, "disk_partitions", lambda *, all: candidates)

    result = inventory.get_linux_mounts({})

    assert len(result["mounts"]) == inventory.MAX_MOUNTS
    assert result["truncated"] is True
    assert result["mounts"][0]["device"] == "nfs://[redacted]@server/share"
    assert result["mounts"][0]["read_only"] is True
    assert result["mount_options_collected"] is False
    assert "lab-password" not in json.dumps(result)


def test_safe_environment_overview_never_returns_values_or_sensitive_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASHBORNE_PUBLIC_LABEL", "unique-visible-value")
    monkeypatch.setenv("ASHBORNE_PASSWORD", "unique-password-value")
    monkeypatch.setenv("ashborne_api_token", "unique-token-value")
    monkeypatch.setenv("COOKIE_JAR", "unique-cookie-value")

    result = inventory.get_safe_environment_overview({})
    encoded = json.dumps(result)

    assert "ASHBORNE_PUBLIC_LABEL" in result["names"]
    assert "ASHBORNE_PASSWORD" not in result["names"]
    assert "ashborne_api_token" not in result["names"]
    assert "COOKIE_JAR" not in result["names"]
    assert result["values_collected"] is False
    assert result["filtered_names_collected"] is False
    assert "unique-visible-value" not in encoded
    assert "unique-password-value" not in encoded
    assert "unique-token-value" not in encoded
    assert "unique-cookie-value" not in encoded
    for name in result["names"]:
        assert not any(part in name.upper() for part in inventory.SENSITIVE_ENVIRONMENT_NAME_PARTS)


def test_linux_service_overview_collects_names_only_and_caps_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    units = tmp_path / "units"
    units.mkdir()
    for index in range(inventory.MAX_SERVICES + 2):
        (units / f"lab-{index:03}.service").write_text(
            "ExecStart=/bin/never-collect-this --secret=value",
            encoding="utf-8",
        )
    (units / "not-a-unit.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory, "SYSTEMD_SERVICE_DIRS", (units,))

    result = inventory.get_service_overview({})
    encoded = json.dumps(result)

    assert result["supported"] is True
    assert len(result["services"]) == inventory.MAX_SERVICES
    assert result["truncated"] is True
    assert result["unit_contents_collected"] is False
    assert all(item["name"].endswith(".service") for item in result["services"])
    assert "never-collect-this" not in encoded
    assert "secret=value" not in encoded


def test_scheduled_activity_collects_fixed_location_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crontab = tmp_path / "crontab"
    cron_dir = tmp_path / "cron.daily"
    unit_dir = tmp_path / "units"
    cron_dir.mkdir()
    unit_dir.mkdir()
    crontab.write_text("* * * * * collect-this-never", encoding="utf-8")
    (cron_dir / "nightly-lab").write_text("secret-command", encoding="utf-8")
    (unit_dir / "lab.timer").write_text("OnCalendar=*-*-*", encoding="utf-8")
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory, "CRON_PATHS", (crontab, cron_dir))
    monkeypatch.setattr(inventory, "SYSTEMD_SERVICE_DIRS", (unit_dir,))

    result = inventory.get_scheduled_activity_overview({})
    encoded = json.dumps(result)
    names = {item["name"] for item in result["activities"]}

    assert result["supported"] is True
    assert {"crontab", "nightly-lab", "lab.timer"} <= names
    assert result["definitions_collected"] is False
    assert result["commands_collected"] is False
    assert "collect-this-never" not in encoded
    assert "secret-command" not in encoded
    assert "OnCalendar" not in encoded


def test_network_overview_is_passive_and_uses_fixed_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory, "get_network_interfaces", lambda _: {"interfaces": []})
    monkeypatch.setattr(inventory, "get_route_table", lambda _: {"routes": []})
    monkeypatch.setattr(
        inventory,
        "get_listening_ports",
        lambda parameters: {"limit": parameters["limit"]},
    )
    monkeypatch.setattr(
        inventory,
        "get_network_connections",
        lambda parameters: {"limit": parameters["limit"]},
    )

    result = inventory.get_network_overview({})

    assert result["scope"] == "local_host_only"
    assert result["active_network_probing"] is False
    assert result["dns_resolution_performed"] is False
    assert result["listening_ports"]["limit"] == 100
    assert result["connections"]["limit"] == 100


def test_privilege_enumeration_is_observational_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory.platform, "system", lambda: "Linux")
    monkeypatch.setattr(inventory, "get_linux_identity", lambda _: {"supported": True})
    monkeypatch.setattr(inventory, "get_group_membership", lambda _: {"supported": True})
    monkeypatch.setattr(inventory, "get_linux_capabilities", lambda _: {"supported": True})

    result = inventory.get_privilege_enumeration({})

    assert result["scope"] == "current_process_and_user"
    assert result["privilege_escalation_attempted"] is False
    assert result["credential_material_collected"] is False
    assert result["policy_files_read"] is False


def test_host_recon_preserves_explicit_safety_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "get_system_info",
        "get_linux_kernel_info",
        "get_uptime",
        "get_privilege_enumeration",
        "get_network_overview",
        "get_linux_mounts",
        "get_service_overview",
        "get_scheduled_activity_overview",
        "get_safe_environment_overview",
    ):
        monkeypatch.setattr(inventory, name, lambda _, name=name: {"collector": name})

    result = inventory.get_host_recon({})

    assert result["scope"] == "local_host_only"
    assert result["active_network_probing"] is False
    assert result["credential_material_collected"] is False
    assert result["arbitrary_paths_accepted"] is False
    assert result["network"] == {"collector": "get_network_overview"}
