import { describe, expect, it } from "vitest";
import {
  operatorCommandCompletions,
  parseOperatorCommand,
} from "./operatorCommands";

describe("operator command parser", () => {
  it.each([
    ["hostname", "HOSTNAME"],
    ["whoami", "CURRENT_USER"],
    ["id", "LINUX_IDENTITY"],
    ["uname -a", "LINUX_KERNEL_INFO"],
    ["ps aux", "PROCESS_INVENTORY"],
    ["ip addr", "NETWORK_INTERFACES"],
    ["ip route", "ROUTE_TABLE"],
    ["ss -tulpn", "NETWORK_CONNECTIONS"],
    ["df -h", "DISK_USAGE"],
    ["mount", "LINUX_MOUNTS"],
    ["env", "SAFE_ENVIRONMENT_OVERVIEW"],
    ["quick-recon", "QUICK_RECON"],
    ["host-recon", "HOST_RECON"],
    ["priv-enum", "PRIVILEGE_ENUMERATION"],
  ])("maps %s to the typed %s action", (command, action) => {
    expect(parseOperatorCommand(`  ${command}  `)).toEqual({
      kind: "action",
      command,
      action,
    });
  });

  it("keeps workspace commands local and never treats unknown text as a task", () => {
    expect(parseOperatorCommand("deselect-all")).toEqual({
      kind: "local",
      command: "deselect-all",
    });
    expect(parseOperatorCommand("curl example.invalid")).toEqual({
      kind: "unsupported",
      command: "curl example.invalid",
    });
  });

  it("offers bounded prefix completion", () => {
    expect(operatorCommandCompletions("quick-r")).toEqual(["quick-recon"]);
    expect(operatorCommandCompletions("deselect-a")).toEqual([
      "deselect-all",
    ]);
  });
});
