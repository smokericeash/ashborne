import type { TaskType } from "../types";

export const LOCAL_COMMANDS = [
  "help",
  "clear",
  "hosts",
  "select-all",
  "deselect-all",
  "deselect",
  "tasks",
  "status",
] as const;
export type LocalOperatorCommand = (typeof LOCAL_COMMANDS)[number];

const ACTION_ALIASES: Record<string, TaskType> = {
  hostname: "HOSTNAME",
  whoami: "CURRENT_USER",
  id: "LINUX_IDENTITY",
  uname: "LINUX_KERNEL_INFO",
  "uname -a": "LINUX_KERNEL_INFO",
  ps: "PROCESS_INVENTORY",
  "ps aux": "PROCESS_INVENTORY",
  "ps -aux": "PROCESS_INVENTORY",
  "ip addr": "NETWORK_INTERFACES",
  "ip address": "NETWORK_INTERFACES",
  ifconfig: "NETWORK_INTERFACES",
  "ip route": "ROUTE_TABLE",
  route: "ROUTE_TABLE",
  ss: "NETWORK_CONNECTIONS",
  "ss -tulpn": "NETWORK_CONNECTIONS",
  netstat: "NETWORK_CONNECTIONS",
  "netstat -tulpn": "NETWORK_CONNECTIONS",
  df: "DISK_USAGE",
  "df -h": "DISK_USAGE",
  mount: "LINUX_MOUNTS",
  env: "SAFE_ENVIRONMENT_OVERVIEW",
  "quick-recon": "QUICK_RECON",
  "host-recon": "HOST_RECON",
  "priv-enum": "PRIVILEGE_ENUMERATION",
};

export const OPERATOR_COMMANDS = [
  ...LOCAL_COMMANDS,
  ...Object.keys(ACTION_ALIASES),
].sort();

export type ParsedOperatorCommand =
  | { kind: "empty" }
  | { kind: "local"; command: LocalOperatorCommand }
  | { kind: "action"; action: TaskType; command: string }
  | { kind: "unsupported"; command: string };

export function normalizeOperatorCommand(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

export function parseOperatorCommand(value: string): ParsedOperatorCommand {
  const command = normalizeOperatorCommand(value);
  if (!command) return { kind: "empty" };
  if ((LOCAL_COMMANDS as readonly string[]).includes(command)) {
    return { kind: "local", command: command as LocalOperatorCommand };
  }
  const action = ACTION_ALIASES[command];
  if (action) return { kind: "action", action, command };
  return { kind: "unsupported", command };
}

export function operatorCommandCompletions(value: string) {
  const command = normalizeOperatorCommand(value);
  if (!command) return [];
  return OPERATOR_COMMANDS.filter((candidate) => candidate.startsWith(command));
}
