export const LOCAL_COMMANDS = [
  "help",
  "clear",
  "hosts",
  "select-all",
  "deselect-all",
  "deselect",
  "tasks",
  "status",
  "retry failed",
] as const;
export type LocalOperatorCommand = (typeof LOCAL_COMMANDS)[number];

const COMMON_OPERATIONS = [
  "hostname",
  "whoami",
  "id",
  "uname -a",
  "ps aux",
  "ip addr",
  "ip route",
  "ss -tulpn",
  "df -h",
  "mount",
  "env",
];

export const OPERATOR_COMMANDS = [
  ...LOCAL_COMMANDS,
  ...COMMON_OPERATIONS,
].sort();

export type ParsedOperatorCommand =
  | { kind: "empty" }
  | { kind: "local"; command: LocalOperatorCommand }
  | { kind: "operation"; command: string; executionMode: "ssh" | "local" };

export function normalizeOperatorCommand(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

export function parseOperatorCommand(value: string): ParsedOperatorCommand {
  const raw = value.trim();
  const normalized = normalizeOperatorCommand(raw);
  if (!raw) return { kind: "empty" };
  if ((LOCAL_COMMANDS as readonly string[]).includes(normalized)) {
    return { kind: "local", command: normalized as LocalOperatorCommand };
  }
  if (normalized.startsWith("kali:")) {
    const separator = raw.indexOf(":");
    const command = raw.slice(separator + 1).trim();
    return command
      ? { kind: "operation", command, executionMode: "local" }
      : { kind: "empty" };
  }
  return { kind: "operation", command: raw, executionMode: "ssh" };
}

export function operatorCommandCompletions(value: string) {
  const command = normalizeOperatorCommand(value);
  if (!command) return [];
  return OPERATOR_COMMANDS.filter((candidate) => candidate.startsWith(command));
}
