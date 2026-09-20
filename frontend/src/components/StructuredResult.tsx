import { Clipboard, Clock3, FileJson, ListTree } from "lucide-react";
import { memo, useMemo, useState } from "react";
import { formatBytes, formatDate, formatDuration, humanize } from "../lib/utils";
import type { AshborneTask } from "../types";
import { EmptyState, StatusBadge } from "./ui";

type ResultTab = "summary" | "raw" | "timeline" | "audit";
type RecordValue = Record<string, any>;

function asRecord(value: unknown): RecordValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordValue)
    : null;
}

function resultPayload(result: unknown) {
  const envelope = asRecord(result);
  return asRecord(envelope?.data) ?? envelope;
}

function valueText(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(valueText).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ResultTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: Array<Array<unknown>>;
}) {
  if (!rows.length)
    return (
      <EmptyState
        title="No observations"
        description="The agent returned no rows for this result set."
      />
    );
  return (
    <div className="overflow-x-auto rounded-lg border border-line/60">
      <table className="w-full">
        <thead className="bg-black/20">
          <tr>
            {headers.map((header) => (
              <th key={header} className="table-heading">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line/40">
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((value, column) => (
                <td key={column} className="table-cell font-mono text-xs">
                  {valueText(value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KeyValueSummary({ value }: { value: RecordValue }) {
  const entries = Object.entries(value)
    .filter(([, item]) => item == null || typeof item !== "object")
    .slice(0, 18);
  if (!entries.length)
    return (
      <EmptyState
        title="Nested result"
        description="Use Raw to inspect the complete structured response."
      />
    );
  return (
    <dl className="grid gap-px overflow-hidden rounded-lg border border-line/60 bg-line/40 sm:grid-cols-2">
      {entries.map(([key, item]) => (
        <div key={key} className="min-w-0 bg-panel px-4 py-3">
          <dt className="text-[9px] font-semibold uppercase tracking-[.14em] text-slate-600">
            {humanize(key)}
          </dt>
          <dd className="mt-1 break-words font-mono text-xs text-slate-200">
            {key.endsWith("_seconds") && typeof item === "number"
              ? formatDuration(item)
              : valueText(item)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Summary({ task }: { task: AshborneTask }) {
  const data = resultPayload(task.result);
  if (!data)
    return (
      <EmptyState
        title="Result pending"
        description="A structured summary will appear when the host completes this task."
      />
    );

  const system = asRecord(data.system) ?? data;
  if (
    ["SYSTEM_INFO", "QUICK_RECON", "HOST_RECON", "LINUX_KERNEL_INFO"].includes(
      task.task_type,
    )
  ) {
    return (
      <div className="space-y-4">
        <KeyValueSummary value={system} />
        {(task.task_type === "QUICK_RECON" || task.task_type === "HOST_RECON") && (
          <p className="text-[11px] text-slate-600">
            This is the primary host summary. Nested network, privilege, and
            filesystem observations remain available under Raw.
          </p>
        )}
      </div>
    );
  }

  const interfaceSource = asRecord(data.interfaces) ?? data;
  const interfaces = Array.isArray(interfaceSource.interfaces)
    ? interfaceSource.interfaces
    : [];
  if (task.task_type === "NETWORK_INTERFACES") {
    const rows = interfaces.flatMap((item: RecordValue) => {
      const addresses = Array.isArray(item.addresses) ? item.addresses : [];
      return addresses.length
        ? addresses.map((address: unknown) => [
          item.name,
          asRecord(address)?.address ?? address,
          item.is_up === true ? "UP" : item.is_up === false ? "DOWN" : "—",
        ])
        : [[item.name, "—", item.is_up ? "UP" : "DOWN"]];
    });
    return <ResultTable headers={["Interface", "Address", "State"]} rows={rows} />;
  }

  const processes = Array.isArray(data.processes) ? data.processes : [];
  if (task.task_type === "PROCESS_INVENTORY")
    return (
      <ResultTable
        headers={["PID", "User", "Process", "State", "Memory"]}
        rows={processes.map((process: RecordValue) => [
          process.pid,
          process.username,
          process.name,
          process.status,
          process.memory_percent == null ? null : `${process.memory_percent}%`,
        ])}
      />
    );

  const listeners = Array.isArray(data.listeners) ? data.listeners : [];
  if (task.task_type === "LISTENING_PORTS")
    return (
      <ResultTable
        headers={["Protocol", "Address", "Port", "Process"]}
        rows={listeners.map((port: RecordValue) => [
          String(port.transport ?? port.protocol ?? "").toUpperCase(),
          port.local_address ?? port.address,
          port.local_port ?? port.port,
          port.process_name ?? port.process,
        ])}
      />
    );

  const connections = Array.isArray(data.connections) ? data.connections : [];
  if (task.task_type === "NETWORK_CONNECTIONS")
    return (
      <ResultTable
        headers={["Protocol", "Local", "Remote", "State", "Process"]}
        rows={connections.map((connection: RecordValue) => [
          String(connection.transport ?? "").toUpperCase(),
          valueText(connection.local),
          valueText(connection.remote),
          connection.status,
          connection.process_name,
        ])}
      />
    );

  const disks = Array.isArray(data.partitions)
    ? data.partitions
    : Array.isArray(data.mounts)
      ? data.mounts
      : [];
  if (task.task_type === "DISK_USAGE" || task.task_type === "LINUX_MOUNTS")
    return (
      <ResultTable
        headers={["Mount", "Filesystem", "Total", "Free", "Used"]}
        rows={disks.map((disk: RecordValue) => [
          disk.mountpoint,
          disk.filesystem,
          disk.total_bytes == null ? disk.device : formatBytes(disk.total_bytes),
          disk.free_bytes == null ? null : formatBytes(disk.free_bytes),
          disk.used_percent == null ? null : `${disk.used_percent}%`,
        ])}
      />
    );

  return <KeyValueSummary value={data} />;
}

function Timeline({ task }: { task: AshborneTask }) {
  const events = [
    ["Created", task.created_at],
    ["Dispatched", task.dispatched_at],
    ["Started", task.started_at],
    [task.status === "FAILED" ? "Failed" : "Completed", task.completed_at],
  ].filter((event): event is [string, string] => Boolean(event[1]));
  return (
    <ol className="space-y-3">
      {events.map(([label, timestamp], index) => (
        <li key={label} className="flex gap-3">
          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-ashborne-400" />
          <div>
            <p className="text-xs font-medium text-slate-200">{label}</p>
            <p className="font-mono text-[10px] text-slate-600">
              {formatDate(timestamp)}
            </p>
          </div>
          {index === events.length - 1 && (
            <div className="ml-auto">
              <StatusBadge status={task.status} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

export const StructuredResult = memo(function StructuredResult({
  task,
}: {
  task: AshborneTask;
}) {
  const [tab, setTab] = useState<ResultTab>("summary");
  const raw = useMemo(
    () =>
      task.result == null
        ? "No result is available yet."
        : JSON.stringify(task.result, null, 2),
    [task.result],
  );
  const tabs: Array<{ id: ResultTab; label: string; icon: typeof ListTree }> = [
    { id: "summary", label: "Summary", icon: ListTree },
    { id: "raw", label: "Raw", icon: FileJson },
    { id: "timeline", label: "Timeline", icon: Clock3 },
    { id: "audit", label: "Audit", icon: Clipboard },
  ];
  return (
    <div>
      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-line/60">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition ${tab === item.id
                ? "border-ashborne-400 text-slate-100"
                : "border-transparent text-slate-600 hover:text-slate-300"
              }`}
            onClick={() => setTab(item.id)}
          >
            <item.icon className="h-3.5 w-3.5" /> {item.label}
          </button>
        ))}
      </div>
      {tab === "summary" && <Summary task={task} />}
      {tab === "raw" && (
        <pre className="max-h-[48vh] overflow-auto rounded-lg bg-black/30 p-4 text-xs leading-5 text-slate-400">
          {raw}
        </pre>
      )}
      {tab === "timeline" && <Timeline task={task} />}
      {tab === "audit" &&
        (task.audit_events?.length ? (
          <div className="divide-y divide-line/40 rounded-lg border border-line/60">
            {task.audit_events.map((event) => (
              <div key={event.id} className="flex justify-between gap-3 p-3">
                <span className="font-mono text-xs text-slate-300">
                  {event.event_type}
                </span>
                <span className="text-[10px] text-slate-600">
                  {formatDate(event.timestamp)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg bg-void/50 p-4 text-xs leading-5 text-slate-500">
            Audit events are retained in the immutable audit ledger and linked
            by task UUID <span className="font-mono text-slate-300">{task.id}</span>.
          </div>
        ))}
    </div>
  );
});
