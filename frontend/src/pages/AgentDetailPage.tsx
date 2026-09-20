import {
  Activity,
  ArrowLeft,
  Box,
  Cpu,
  HardDrive,
  MemoryStick,
  Network,
  RadioTower,
  Server,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PermissionGate } from "../components/auth/ProtectedRoute";
import { TaskForm } from "../components/TaskForm";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  KeyValue,
  Modal,
  PageHeader,
  SectionTitle,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useAgentsRevision, useTasksRevision } from "../context/useLive";
import { useToast } from "../context/useToast";
import { useResource } from "../hooks/useResource";
import {
  formatBytes,
  formatDate,
  formatDuration,
  formatRelativeTime,
  humanize,
} from "../lib/utils";
import { api, inventoryFromTasks } from "../services/api";
import type { AgentInventory, AshborneTask } from "../types";

type Tab = "overview" | "inventory" | "tasks";

function ProgressBar({
  value,
  tone = "cyan",
}: {
  value?: number;
  tone?: "cyan" | "amber" | "red";
}) {
  const safeValue = Math.max(0, Math.min(100, value ?? 0));
  const color =
    tone === "red"
      ? "bg-red-400"
      : tone === "amber"
        ? "bg-amber-400"
        : "bg-ashborne-400";
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-white/[.04]">
      <div
        className={`h-full rounded-full ${color}`}
        style={{ width: `${safeValue}%` }}
      />
    </div>
  );
}

function OverviewPanel({
  agent,
}: {
  agent: NonNullable<ReturnType<typeof useAgentData>["data"]>["agent"];
}) {
  const heartbeats = agent.heartbeat_history ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
      <Card className="overflow-hidden">
        <SectionTitle
          title="Lab-host identity"
          description="Agent-reported host attributes"
        />
        <dl className="grid grid-cols-1 gap-x-6 px-5 sm:grid-cols-2">
          <KeyValue label="Agent UUID" value={agent.uuid || agent.id} mono />
          <KeyValue label="Hostname" value={agent.hostname} mono />
          <KeyValue label="Current user" value={agent.username} />
          <KeyValue label="IP address" value={agent.ip_address} mono />
          <KeyValue
            label="Operating system"
            value={`${agent.operating_system}${agent.os_version ? ` ${agent.os_version}` : ""}`}
          />
          <KeyValue label="Architecture" value={agent.architecture} mono />
          <KeyValue label="Agent version" value={agent.agent_version} mono />
          <KeyValue
            label="First observed"
            value={formatDate(agent.first_seen)}
          />
        </dl>
      </Card>

      <Card className="overflow-hidden">
        <SectionTitle
          title="Heartbeat health"
          description="Status derived from configurable check-in thresholds"
        />
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-line bg-void/40 p-3">
              <p className="text-[9px] uppercase tracking-wider text-slate-600">
                Current state
              </p>
              <div className="mt-2">
                <StatusBadge status={agent.status} />
              </div>
            </div>
            <div className="rounded-lg border border-line bg-void/40 p-3">
              <p className="text-[9px] uppercase tracking-wider text-slate-600">
                Last check-in
              </p>
              <p className="mt-2 text-sm font-medium text-slate-200">
                {formatRelativeTime(agent.last_seen)}
              </p>
            </div>
            <div className="rounded-lg border border-line bg-void/40 p-3">
              <p className="text-[9px] uppercase tracking-wider text-slate-600">
                Uptime
              </p>
              <p className="mt-2 text-sm font-medium text-slate-200">
                {formatDuration(agent.uptime_seconds)}
              </p>
            </div>
          </div>
          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[.12em] text-slate-500">
                Recent signal
              </p>
              <p className="text-[10px] text-slate-600">
                {heartbeats.length} observations
              </p>
            </div>
            {heartbeats.length ? (
              <div className="flex h-20 items-end gap-1 rounded-lg border border-line bg-void/40 p-3">
                {[...heartbeats]
                  .reverse()
                  .slice(-32)
                  .map((heartbeat, index) => {
                    const height = 35 + ((index * 17) % 60);
                    const color =
                      heartbeat.status === "OFFLINE"
                        ? "bg-red-400"
                        : heartbeat.status === "DEGRADED"
                          ? "bg-amber-400"
                          : "bg-ashborne-400";
                    return (
                      <div
                        key={heartbeat.id ?? `${heartbeat.timestamp}-${index}`}
                        title={`${formatDate(heartbeat.timestamp)} · ${heartbeat.status ?? "ONLINE"}`}
                        className={`min-w-1 flex-1 rounded-t-sm opacity-70 transition hover:opacity-100 ${color}`}
                        style={{ height: `${height}%` }}
                      />
                    );
                  })}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-line p-6 text-center text-xs text-slate-600">
                Heartbeat history will accumulate here.
              </div>
            )}
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden xl:col-span-2">
        <SectionTitle
          title="Classification"
          description="Operator-assigned labels for lab organization"
        />
        <div className="flex min-h-20 flex-wrap items-center gap-2 p-5">
          {agent.tags?.length ? (
            agent.tags.map((tag) => (
              <Badge key={tag} tone="info">
                {tag}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-slate-600">No tags assigned</span>
          )}
        </div>
      </Card>
    </div>
  );
}

function InventoryPanel({ inventory }: { inventory?: AgentInventory | null }) {
  if (!inventory)
    return (
      <Card>
        <EmptyState
          title="No inventory snapshot"
          description="Issue Quick Recon or a typed enumeration action to collect structured host observations."
          icon={<Box className="h-5 w-5" />}
        />
      </Card>
    );
  const memoryTone =
    (inventory.memory?.used_percent ?? 0) >= 90
      ? "red"
      : (inventory.memory?.used_percent ?? 0) >= 75
        ? "amber"
        : "cyan";
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                CPU utilization
              </p>
              <p className="mt-2 text-2xl font-semibold text-white">
                {inventory.cpu?.usage_percent?.toFixed(1) ?? "—"}
                <span className="text-sm text-slate-600">%</span>
              </p>
            </div>
            <Cpu className="h-5 w-5 text-ashborne-400" />
          </div>
          <div className="mt-4">
            <ProgressBar value={inventory.cpu?.usage_percent} />
          </div>
          <p className="mt-3 truncate text-[11px] text-slate-600">
            {inventory.cpu?.model ||
              `${inventory.cpu?.logical_cores ?? "—"} logical cores`}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                Memory utilization
              </p>
              <p className="mt-2 text-2xl font-semibold text-white">
                {inventory.memory?.used_percent?.toFixed(1) ?? "—"}
                <span className="text-sm text-slate-600">%</span>
              </p>
            </div>
            <MemoryStick className="h-5 w-5 text-cyan-400" />
          </div>
          <div className="mt-4">
            <ProgressBar
              value={inventory.memory?.used_percent}
              tone={memoryTone}
            />
          </div>
          <p className="mt-3 text-[11px] text-slate-600">
            {formatBytes(inventory.memory?.available_bytes)} free of{" "}
            {formatBytes(inventory.memory?.total_bytes)}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                Storage volumes
              </p>
              <p className="mt-2 text-2xl font-semibold text-white">
                {inventory.disks?.length ?? 0}
              </p>
            </div>
            <HardDrive className="h-5 w-5 text-violet-400" />
          </div>
          <p className="mt-7 text-[11px] text-slate-600">
            Observed mounted filesystems
          </p>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <SectionTitle
          title="Storage"
          description="Mounted filesystem utilization"
        />
        {inventory.disks?.length ? (
          <div className="divide-y divide-line/50">
            {inventory.disks.map((disk) => (
              <div
                key={disk.mountpoint}
                className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_160px_120px] sm:items-center"
              >
                <div>
                  <p className="font-mono text-xs text-slate-200">
                    {disk.mountpoint}
                  </p>
                  <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">
                    {disk.filesystem || "Unknown filesystem"}
                  </p>
                </div>
                <ProgressBar
                  value={disk.used_percent}
                  tone={
                    (disk.used_percent ?? 0) >= 90
                      ? "red"
                      : (disk.used_percent ?? 0) >= 75
                        ? "amber"
                        : "cyan"
                  }
                />
                <p className="text-right text-xs text-slate-500">
                  {disk.used_percent?.toFixed(1) ?? "—"}% ·{" "}
                  {formatBytes(disk.free_bytes)} free
                </p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No disk data"
            description="No mounted storage was reported in this snapshot."
          />
        )}
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <InventoryTable
          title="Network interfaces"
          description="Reported interfaces and addresses"
          icon={<Network className="h-4 w-4" />}
          headers={["Interface", "Address", "State"]}
          rows={(inventory.interfaces ?? []).map((item) => [
            item.name,
            item.addresses?.join(", ") || "—",
            item.is_up === false ? "Down" : "Up",
          ])}
        />
        <InventoryTable
          title="Listening ports"
          description="Locally observed listening sockets"
          icon={<RadioTower className="h-4 w-4" />}
          headers={["Socket", "Protocol", "Process"]}
          rows={(inventory.listening_ports ?? [])
            .slice(0, 50)
            .map((item) => [
              `${item.address}:${item.port}`,
              item.protocol,
              item.process || (item.pid ? `PID ${item.pid}` : "—"),
            ])}
        />
        <InventoryTable
          title="Processes"
          description="Structured process inventory; no remote execution"
          icon={<Activity className="h-4 w-4" />}
          headers={["PID", "Process", "User"]}
          rows={(inventory.processes ?? [])
            .slice(0, 50)
            .map((item) => [String(item.pid), item.name, item.username || "—"])}
        />
        <InventoryTable
          title="Installed software"
          description="Reported packages and versions"
          icon={<Box className="h-4 w-4" />}
          headers={["Package", "Version"]}
          rows={(inventory.installed_software ?? [])
            .slice(0, 50)
            .map((item) => [item.name, item.version || "—"])}
        />
      </div>
    </div>
  );
}

function InventoryTable({
  title,
  description,
  icon,
  headers,
  rows,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  headers: string[];
  rows: string[][];
}) {
  return (
    <Card className="overflow-hidden">
      <SectionTitle
        title={title}
        description={description}
        action={<span className="text-slate-600">{icon}</span>}
      />
      {rows.length ? (
        <div className="max-h-80 overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-panel">
              <tr>
                {headers.map((header) => (
                  <th key={header} className="table-heading">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line/50">
              {rows.map((row, index) => (
                <tr key={`${row[0]}-${index}`}>
                  {row.map((value, cellIndex) => (
                    <td
                      key={`${value}-${cellIndex}`}
                      className="table-cell max-w-64 truncate"
                    >
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title={`No ${title.toLowerCase()}`}
          description="This field was empty in the most recent inventory snapshot."
        />
      )}
    </Card>
  );
}

function TasksPanel({
  tasks,
  agentId,
  agentName,
  onCreated,
  onInspect,
}: {
  tasks: AshborneTask[];
  agentId: string;
  agentName: string;
  onCreated: (task: AshborneTask) => void;
  onInspect: (task: AshborneTask) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <Card className="min-w-0 overflow-hidden">
        <SectionTitle
          title="Task history"
          description="Authorized typed actions issued to this lab host"
        />
        {tasks.length ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line/70">
                  <th className="table-heading">Task</th>
                  <th className="table-heading">Operator</th>
                  <th className="table-heading">Created</th>
                  <th className="table-heading">Status</th>
                  <th className="table-heading">
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/50">
                {tasks.map((task) => (
                  <tr key={task.id} className="hover:bg-white/[.02]">
                    <td className="table-cell">
                      <p className="font-mono text-xs text-slate-200">
                        {task.task_type}
                      </p>
                      <p className="mt-0.5 max-w-36 truncate font-mono text-[9px] text-slate-700">
                        {task.id}
                      </p>
                    </td>
                    <td className="table-cell">
                      {task.requested_by_email || task.requested_by || "System"}
                    </td>
                    <td className="table-cell">
                      {formatDate(task.created_at)}
                    </td>
                    <td className="table-cell">
                      <StatusBadge status={task.status} />
                    </td>
                    <td className="table-cell text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onInspect(task)}
                      >
                        Inspect
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No task history"
            description="Queue an approved lab action to start a structured task history."
          />
        )}
      </Card>
      <Card className="h-fit overflow-hidden">
        <SectionTitle
          title="Issue lab action"
          description={`Target: ${agentName}`}
        />
        <div className="p-5">
          <TaskForm
            agentId={agentId}
            agentName={agentName}
            onCreated={onCreated}
          />
        </div>
      </Card>
    </div>
  );
}

function useAgentData(id: string, revision: number) {
  return useResource(async () => {
    const [agent, tasks] = await Promise.all([
      api.agents.get(id),
      api.tasks.list({ agent_id: id, skip: 0, limit: 100 }),
    ]);
    const allTasks = tasks.items.length
      ? tasks.items
      : (agent.recent_tasks ?? []);
    return {
      agent: {
        ...agent,
        inventory:
          agent.inventory ??
          inventoryFromTasks([...(agent.recent_tasks ?? []), ...allTasks]),
      },
      tasks: allTasks,
    };
  }, [id, revision]);
}

export function AgentDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const agentsRevision = useAgentsRevision();
  const tasksRevision = useTasksRevision();
  const { notify } = useToast();
  const resource = useAgentData(id, agentsRevision + tasksRevision);
  const [tab, setTab] = useState<Tab>("overview");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [inspectedTask, setInspectedTask] = useState<AshborneTask | null>(null);

  if (resource.loading)
    return (
      <>
        <PageHeader title="Lab-host intelligence" />
        <Spinner label="Resolving lab-host identity" />
      </>
    );
  if (resource.error || !resource.data)
    return (
      <>
        <PageHeader title="Lab-host intelligence" />
        <Card>
          <ErrorState
            error={resource.error ?? "Agent not found"}
            onRetry={() => void resource.reload()}
          />
        </Card>
      </>
    );
  const { agent, tasks } = resource.data;

  const removeAgent = async () => {
    setDeleting(true);
    try {
      await api.agents.remove(agent.id);
      notify(`${agent.name || agent.hostname} removed from ASHBORNE.`);
      navigate("/agents", { replace: true });
    } catch (caught) {
      notify(
        caught instanceof Error
          ? caught.message
          : "Agent could not be removed.",
        "error",
      );
      setDeleting(false);
    }
  };

  const addTask = (task: AshborneTask) => {
    resource.data?.tasks.unshift(task);
    void resource.reload();
  };

  return (
    <div className="animate-slide-in">
      <Link
        to="/agents"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-ashborne-300"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> Back to lab hosts
      </Link>
      <PageHeader
        eyebrow="In-scope host intelligence"
        title={agent.name || agent.hostname}
        description={`${agent.hostname} · ${agent.operating_system} ${agent.os_version ?? ""}`}
        actions={
          <>
            <StatusBadge status={agent.status} />
            <PermissionGate roles={["ADMINISTRATOR"]}>
              <Button
                size="sm"
                variant="danger"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="h-3.5 w-3.5" /> Remove
              </Button>
            </PermissionGate>
          </>
        }
      />

      <div className="mb-4 flex overflow-x-auto rounded-lg border border-line bg-panel/70 p-1">
        {(["overview", "inventory", "tasks"] as Tab[]).map((item) => (
          <button
            key={item}
            className={`min-w-28 rounded-md px-4 py-2 text-xs font-semibold capitalize transition ${tab === item ? "bg-ashborne-400/10 text-ashborne-200" : "text-slate-500 hover:text-slate-200"}`}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewPanel agent={agent} />}
      {tab === "inventory" && <InventoryPanel inventory={agent.inventory} />}
      {tab === "tasks" && (
        <TasksPanel
          tasks={tasks}
          agentId={agent.id}
          agentName={agent.name || agent.hostname}
          onCreated={addTask}
          onInspect={setInspectedTask}
        />
      )}

      <Modal
        open={confirmDelete}
        title="Remove agent?"
        description="This revokes the host credential and removes it from the active lab."
        onClose={() => setConfirmDelete(false)}
      >
        <div className="p-5">
          <div className="flex gap-3 rounded-lg border border-red-500/20 bg-red-500/[.06] p-4">
            <Server className="h-5 w-5 shrink-0 text-red-400" />
            <p className="text-xs leading-5 text-slate-400">
              Remove{" "}
              <strong className="text-slate-200">
                {agent.name || agent.hostname}
              </strong>
              ? Historical audit records remain immutable.
            </p>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deleting}
              onClick={() => void removeAgent()}
            >
              Remove agent
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(inspectedTask)}
        title={
          inspectedTask ? humanize(inspectedTask.task_type) : "Task result"
        }
        description={inspectedTask?.id}
        onClose={() => setInspectedTask(null)}
        width="max-w-2xl"
      >
        {inspectedTask && (
          <div className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <StatusBadge status={inspectedTask.status} />
              <span className="text-xs text-slate-600">
                {formatDate(
                  inspectedTask.completed_at || inspectedTask.created_at,
                )}
              </span>
            </div>
            {inspectedTask.error_message && (
              <p className="mb-3 rounded-lg border border-red-500/20 bg-red-500/[.06] p-3 text-xs text-red-300">
                {inspectedTask.error_message}
              </p>
            )}
            <pre className="max-h-[50vh] overflow-auto rounded-lg border border-line bg-void p-4 text-xs leading-5 text-slate-400">
              {inspectedTask.result != null
                ? JSON.stringify(inspectedTask.result, null, 2)
                : "No structured result is available yet."}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
