import { CornerDownLeft, ShieldCheck, SquareTerminal } from "lucide-react";
import { useCallback, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Card, PageHeader, StatusBadge } from "../components/ui";
import { useAuth } from "../context/useAuth";
import { useHostSelection } from "../context/useHostSelection";
import { useAgentsRevision, useLiveConnection } from "../context/useLive";
import { useResource } from "../hooks/useResource";
import { canIssueTasks } from "../lib/utils";
import {
  operatorCommandCompletions,
  parseOperatorCommand,
} from "../lib/operatorCommands";
import { api } from "../services/api";

type ConsoleEntry = {
  id: number;
  command?: string;
  tone?: "normal" | "error" | "success";
  lines: string[];
  operationId?: string;
};

const HELP_LINES = [
  "Typed host actions: hostname, whoami, id, uname -a, ps aux, ip addr, ip route,",
  "ss -tulpn, df -h, mount, env, quick-recon, host-recon, priv-enum",
  "Workspace commands: help, clear, hosts, select-all, deselect-all, tasks, status",
  "Only recognized aliases map to closed ASHBORNE task types; arbitrary commands never execute.",
];

export function OperatorConsolePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const connected = useLiveConnection();
  const agentsRevision = useAgentsRevision();
  const selection = useHostSelection();
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [running, setRunning] = useState(false);
  const [entries, setEntries] = useState<ConsoleEntry[]>([
    {
      id: 0,
      lines: [
        'ASHBORNE operator console ready. Type "help" for approved commands.',
      ],
    },
  ]);
  const nextEntryId = useRef(1);
  const hosts = useResource(
    () => api.agents.list({ sort_by: "name", sort_order: "asc", limit: 100 }),
    [agentsRevision],
  );

  const append = useCallback((entry: Omit<ConsoleEntry, "id">) => {
    setEntries((current) => [
      ...current,
      { ...entry, id: nextEntryId.current++ },
    ]);
  }, []);

  const execute = async (raw: string) => {
    const parsed = parseOperatorCommand(raw);
    if (parsed.kind === "empty") return;
    setHistory((current) => [...current.filter((item) => item !== raw), raw]);
    setHistoryIndex(-1);

    if (parsed.kind === "unsupported") {
      append({
        command: raw,
        tone: "error",
        lines: ['Unsupported command.', 'Type "help" for available commands.'],
      });
      return;
    }

    if (parsed.kind === "local") {
      if (parsed.command === "clear") {
        setEntries([]);
        return;
      }
      if (parsed.command === "help") {
        append({ command: raw, lines: HELP_LINES });
        return;
      }
      if (parsed.command === "hosts") {
        append({
          command: raw,
          lines: selection.selectedHosts.length
            ? selection.selectedHosts.map(
                (host) => `${host.hostname.padEnd(28)} ${host.status}`,
              )
            : ["No hosts selected. Use select-all or choose hosts on Lab Hosts."],
        });
        return;
      }
      if (parsed.command === "select-all") {
        const available = hosts.data?.items ?? [];
        selection.selectHosts(available);
        append({
          command: raw,
          tone: "success",
          lines: [`Selected ${available.length} loaded lab hosts.`],
        });
        return;
      }
      if (
        parsed.command === "deselect" ||
        parsed.command === "deselect-all"
      ) {
        selection.clearSelection();
        append({ command: raw, lines: ["Host selection cleared."] });
        return;
      }
      if (parsed.command === "tasks") {
        navigate("/tasks");
        return;
      }
      append({
        command: raw,
        lines: [
          `Event stream: ${connected ? "CONNECTED" : "RECONNECTING"}`,
          `Selected hosts: ${selection.selectedHosts.length}`,
          `Authorization: ${scopeConfirmed ? "CONFIRMED" : "NOT CONFIRMED"}`,
        ],
      });
      return;
    }

    if (!canIssueTasks(user?.role)) {
      append({
        command: raw,
        tone: "error",
        lines: ["Your role is read-only and cannot issue tasks."],
      });
      return;
    }
    if (!selection.selectedHosts.length) {
      append({
        command: raw,
        tone: "error",
        lines: ["No hosts selected. Select hosts before issuing a task."],
      });
      return;
    }
    if (!scopeConfirmed) {
      append({
        command: raw,
        tone: "error",
        lines: ["Confirm authorized scope before issuing a task."],
      });
      return;
    }

    setRunning(true);
    try {
      const operation = await api.tasks.bulkCreate(
        selection.selectedHosts.map((host) => host.id),
        parsed.action,
        true,
      );
      append({
        command: raw,
        tone: "success",
        lines: [
          `${parsed.action} queued for ${operation.target_count} hosts.`,
          `Bulk operation ${operation.bulk_operation_id}`,
        ],
        operationId: operation.bulk_operation_id,
      });
    } catch (caught) {
      append({
        command: raw,
        tone: "error",
        lines: [
          caught instanceof Error
            ? caught.message
            : "The typed task could not be queued.",
        ],
      });
    } finally {
      setRunning(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const command = input;
    setInput("");
    void execute(command);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!history.length) return;
      const next = Math.min(history.length - 1, historyIndex + 1);
      setHistoryIndex(next);
      setInput(history[history.length - 1 - next]);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = historyIndex - 1;
      setHistoryIndex(next);
      setInput(next < 0 ? "" : history[history.length - 1 - next]);
    } else if (event.key === "Tab") {
      event.preventDefault();
      const matches = operatorCommandCompletions(input);
      if (matches.length === 1) setInput(matches[0]);
      else if (matches.length > 1)
        append({ command: input, lines: [matches.join("    ")] });
    }
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Typed operator workflow"
        title="Operator Console"
        description="Terminal ergonomics over explicit, audited ASHBORNE task types — never an arbitrary shell."
        actions={
          <Link to="/agents">
            <Button variant="secondary" size="sm">
              Choose hosts
            </Button>
          </Link>
        }
      />

      <Card className="overflow-hidden border-line/60 bg-[#111011]/95">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <SquareTerminal className="h-4 w-4 text-ashborne-400" />
            <span className="font-mono text-xs font-semibold text-slate-200">
              ASHBORNE
            </span>
            <span className="rounded bg-ashborne-400/10 px-2 py-0.5 font-mono text-[10px] text-ashborne-300">
              {selection.selectedHosts.length} HOSTS
            </span>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-400">
            <input
              aria-label="Confirm authorized scope"
              className="h-4 w-4 accent-ashborne-400"
              type="checkbox"
              checked={scopeConfirmed}
              onChange={(event) => setScopeConfirmed(event.target.checked)}
            />
            <ShieldCheck className="h-3.5 w-3.5 text-ashborne-400" />
            Authorized scope confirmed
          </label>
        </div>

        <div
          className="min-h-[460px] max-h-[62vh] overflow-y-auto p-4 font-mono text-xs leading-6"
          aria-live="polite"
        >
          {entries.map((entry) => (
            <div key={entry.id} className="mb-4">
              {entry.command && (
                <p className="text-slate-200">
                  <span className="text-ashborne-400">
                    ashborne [{selection.selectedHosts.length}] &gt;
                  </span>{" "}
                  {entry.command}
                </p>
              )}
              <div
                className={
                  entry.tone === "error"
                    ? "text-red-300"
                    : entry.tone === "success"
                      ? "text-emerald-300"
                      : "text-slate-500"
                }
              >
                {entry.lines.map((line, index) => (
                  <p key={`${entry.id}-${index}`} className="whitespace-pre-wrap">
                    {line}
                  </p>
                ))}
                {entry.operationId && (
                  <Link
                    className="text-ashborne-300 underline decoration-ashborne-400/40 underline-offset-4"
                    to={`/bulk-operations/${entry.operationId}`}
                  >
                    Open operation
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>

        <form
          className="flex items-center gap-2 border-t border-line/60 bg-black/20 px-4 py-3 font-mono"
          onSubmit={submit}
        >
          <label className="shrink-0 text-xs text-ashborne-400" htmlFor="operator-command">
            ashborne [{selection.selectedHosts.length}] &gt;
          </label>
          <input
            id="operator-command"
            autoComplete="off"
            autoFocus
            className="h-9 min-w-0 flex-1 border-0 bg-transparent px-2 text-sm text-slate-100 outline-none placeholder:text-slate-700"
            placeholder="help"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <Button type="submit" size="sm" disabled={running || !input.trim()} loading={running}>
            <CornerDownLeft className="h-3.5 w-3.5" /> Run
          </Button>
        </form>
      </Card>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-[.12em] text-slate-600">
        <span>Tab autocomplete</span>
        <span>↑ ↓ history</span>
        <span className="flex items-center gap-1">
          Stream <StatusBadge status={connected ? "ONLINE" : "DEGRADED"} />
        </span>
      </div>
    </div>
  );
}
