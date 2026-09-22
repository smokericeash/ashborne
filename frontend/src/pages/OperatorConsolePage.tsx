import { CornerDownLeft, ShieldCheck, SquareTerminal } from "lucide-react";
import {
  useCallback,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
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
  targetCount?: number;
  tone?: "normal" | "error" | "success";
  lines: string[];
  operationId?: string;
};

const HELP_LINES = [
  "Remote host operation: enter a normal Linux command (for example: hostname or uname -a).",
  "Kali-local tooling: prefix with kali: and use $ASHBORNE_TARGET_IP as the selected target.",
  'Example: kali:nmap -sV "$ASHBORNE_TARGET_IP"',
  "Workspace commands: help, clear, hosts, select-all, deselect-all, tasks, status, retry failed",
  "Every operation remains scoped to selected enrolled hosts, RBAC-controlled, bounded, and audited.",
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
  const [running, setRunning] = useState(false);
  const [lastOperationId, setLastOperationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<ConsoleEntry[]>([
    {
      id: 0,
      lines: ['ASHBORNE Kali-backed console ready. Type "help" for usage.'],
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
    const commandEntry = {
      command: raw,
      targetCount: selection.selectedHosts.length,
    };
    setHistory((current) => [...current.filter((item) => item !== raw), raw]);
    setHistoryIndex(-1);

    if (parsed.kind === "local") {
      if (parsed.command === "clear") {
        setEntries([]);
        return;
      }
      if (parsed.command === "help") {
        append({ ...commandEntry, lines: HELP_LINES });
        return;
      }
      if (parsed.command === "hosts") {
        append({
          ...commandEntry,
          lines: selection.selectedHosts.length
            ? selection.selectedHosts.map(
                (host) => `${host.hostname.padEnd(28)} ${host.status}`,
              )
            : [
                "No hosts selected. Use select-all or choose hosts on Lab Hosts.",
              ],
        });
        return;
      }
      if (parsed.command === "select-all") {
        const available = hosts.data?.items ?? [];
        selection.selectHosts(available);
        append({
          ...commandEntry,
          tone: "success",
          lines: [`Selected ${available.length} loaded lab hosts.`],
        });
        return;
      }
      if (parsed.command === "deselect" || parsed.command === "deselect-all") {
        selection.clearSelection();
        append({ ...commandEntry, lines: ["Host selection cleared."] });
        return;
      }
      if (parsed.command === "tasks") {
        navigate("/tasks");
        return;
      }
      if (parsed.command === "retry failed") {
        if (!lastOperationId) {
          append({
            ...commandEntry,
            tone: "error",
            lines: ["No previous bulk operation is available to retry."],
          });
          return;
        }
        setRunning(true);
        try {
          const operation = await api.tasks.retryBulkFailed(
            lastOperationId,
            true,
          );
          setLastOperationId(operation.bulk_operation_id);
          append({
            ...commandEntry,
            tone: "success",
            lines: [
              `Retry queued for ${operation.target_count} unsuccessful hosts.`,
              `Bulk operation ${operation.bulk_operation_id}`,
            ],
            operationId: operation.bulk_operation_id,
          });
        } catch (caught) {
          append({
            ...commandEntry,
            tone: "error",
            lines: [
              caught instanceof Error
                ? caught.message
                : "Retry could not be queued.",
            ],
          });
        } finally {
          setRunning(false);
        }
        return;
      }
      append({
        ...commandEntry,
        lines: [
          `Event stream: ${connected ? "CONNECTED" : "RECONNECTING"}`,
          `Selected hosts: ${selection.selectedHosts.length}`,
          "Environment: AUTHORIZED LAB",
        ],
      });
      return;
    }

    if (!canIssueTasks(user?.role)) {
      append({
        ...commandEntry,
        tone: "error",
        lines: ["Your role is read-only and cannot issue tasks."],
      });
      return;
    }
    if (!selection.selectedHosts.length) {
      append({
        ...commandEntry,
        tone: "error",
        lines: ["No hosts selected. Select hosts before issuing a task."],
      });
      return;
    }
    setRunning(true);
    try {
      const operation = await api.tasks.bulkCreate(
        selection.selectedHosts.map((host) => host.id),
        "KALI_OPERATION",
        true,
        {
          command: parsed.command,
          execution_mode: parsed.executionMode,
          timeout_seconds: 120,
        },
      );
      setLastOperationId(operation.bulk_operation_id);
      append({
        ...commandEntry,
        tone: "success",
        lines: [
          `${parsed.executionMode === "local" ? "Kali-local" : "SSH"} operation queued for ${operation.target_count} hosts.`,
          `Bulk operation ${operation.bulk_operation_id}`,
        ],
        operationId: operation.bulk_operation_id,
      });
    } catch (caught) {
      append({
        ...commandEntry,
        tone: "error",
        lines: [
          caught instanceof Error
            ? caught.message
            : "The Kali-backed operation could not be queued.",
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
        append({
          command: input,
          targetCount: selection.selectedHosts.length,
          lines: [matches.join("    ")],
        });
    } else if (event.key.toLowerCase() === "l" && event.ctrlKey) {
      event.preventDefault();
      setEntries([]);
    }
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Kali-backed operator workflow"
        title="Operator Console"
        description="Audited multi-host operations routed through your explicitly enrolled Kali controller."
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
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[.12em] text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5 text-ashborne-400" />
            Authorized lab
          </div>
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
                    ashborne [
                    {entry.targetCount ?? selection.selectedHosts.length}] &gt;
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
                  <p
                    key={`${entry.id}-${index}`}
                    className="whitespace-pre-wrap"
                  >
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
          <label
            className="shrink-0 text-xs text-ashborne-400"
            htmlFor="operator-command"
          >
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
          <Button
            type="submit"
            size="sm"
            disabled={running || !input.trim()}
            loading={running}
          >
            <CornerDownLeft className="h-3.5 w-3.5" /> Run
          </Button>
        </form>
      </Card>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-[.12em] text-slate-600">
        <span>Tab autocomplete</span>
        <span>↑ ↓ history</span>
        <span>Ctrl+L clear</span>
        <span className="flex items-center gap-1">
          Stream <StatusBadge status={connected ? "ONLINE" : "DEGRADED"} />
        </span>
      </div>
    </div>
  );
}
