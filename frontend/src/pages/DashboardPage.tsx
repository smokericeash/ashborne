import {
  Activity,
  ArrowRight,
  CircleAlert,
  ClipboardList,
  RadioTower,
  ShieldCheck,
} from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionTitle,
  Spinner,
  StatusBadge,
} from "../components/ui";
import {
  useDashboardRevision,
  useLiveConnection,
} from "../context/useLive";
import { useResource } from "../hooks/useResource";
import { formatRelativeTime } from "../lib/utils";
import { api } from "../services/api";

export function DashboardPage() {
  const dashboardRevision = useDashboardRevision();
  const connected = useLiveConnection();
  const resource = useResource(
    async () => {
      const [metrics, activity] = await Promise.all([
        api.dashboard.metrics(),
        api.dashboard.activity(),
      ]);
      return { metrics, activity };
    },
    [dashboardRevision],
  );
  const liveTasks = useMemo(
    () =>
      resource.data?.activity.recent_tasks.filter((task) =>
        ["QUEUED", "DISPATCHED", "RUNNING"].includes(task.status),
      ) ?? [],
    [resource.data],
  );

  if (resource.loading) return <Spinner label="Opening command center" />;
  if (resource.error || !resource.data)
    return (
      <ErrorState
        error={resource.error ?? "Command center data is unavailable"}
        onRetry={() => void resource.reload()}
      />
    );

  const { metrics, activity } = resource.data;
  const cards = [
    {
      label: "Online hosts",
      value: metrics.online_agents,
      detail: `${metrics.total_agents} Lab hosts`,
      icon: ShieldCheck,
      tone: "text-emerald-300",
    },
    {
      label: "Running tasks",
      value: metrics.tasks_running,
      detail: `${metrics.tasks_queued} queued`,
      icon: Activity,
      tone: "text-slate-100",
    },
    {
      label: "Failed tasks",
      value: metrics.tasks_failed,
      detail: `${Math.round(metrics.task_success_rate)}% success`,
      icon: CircleAlert,
      tone: metrics.tasks_failed ? "text-red-300" : "text-slate-100",
    },
    {
      label: "Recent operations",
      value: activity.recent_tasks.length,
      detail: `Avg check-in ${Math.round(metrics.average_check_in_seconds ?? 0)}s`,
      icon: ClipboardList,
      tone: "text-slate-100",
    },
  ];

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Authorized lab overview"
        title="Command Center"
        description="Current host and operation state, without dashboard noise."
        actions={
          <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.14em] text-slate-500">
            <span
              className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`}
            />
            {connected ? "Live" : "Reconnecting"}
          </span>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.label} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[9px] font-bold uppercase tracking-[.16em] text-slate-600">
                  {card.label}
                </p>
                <p className={`mt-2 font-mono text-3xl font-semibold ${card.tone}`}>
                  {card.value}
                </p>
                <p className="mt-1 text-[10px] text-slate-600">{card.detail}</p>
              </div>
              <card.icon className="h-4 w-4 text-slate-700" />
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card className="overflow-hidden">
          <SectionTitle
            title="Live operations"
            description="Queued, dispatched, and running work"
            action={
              <Link
                className="flex items-center gap-1 text-[11px] font-semibold text-ashborne-400"
                to="/tasks"
              >
                All tasks <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
          {liveTasks.length ? (
            <div className="divide-y divide-line/50">
              {liveTasks.slice(0, 8).map((task) => (
                <Link
                  key={task.id}
                  to={`/tasks?focus=${task.id}`}
                  className="flex items-center gap-3 px-4 py-3 transition hover:bg-white/[.025]"
                >
                  <RadioTower className="h-4 w-4 shrink-0 text-slate-700" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-slate-200">
                      {task.task_type}
                    </p>
                    <p className="truncate text-[10px] text-slate-600">
                      {task.agent_name || task.agent_id}
                    </p>
                  </div>
                  <StatusBadge status={task.status} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No live operations"
              description="Queued and running tasks will appear here."
            />
          )}
        </Card>

        <Card className="overflow-hidden">
          <SectionTitle
            title="Recent host activity"
            description="Latest enrolled-host check-ins"
            action={
              <Link
                className="flex items-center gap-1 text-[11px] font-semibold text-ashborne-400"
                to="/agents"
              >
                Lab hosts <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
          {activity.latest_agents.length ? (
            <div className="divide-y divide-line/50">
              {activity.latest_agents.slice(0, 8).map((agent) => (
                <Link
                  key={agent.id}
                  to={`/agents/${agent.id}`}
                  className="flex items-center gap-3 px-4 py-3 transition hover:bg-white/[.025]"
                >
                  <ShieldCheck className="h-4 w-4 shrink-0 text-slate-700" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-200">
                      {agent.name || agent.hostname}
                    </p>
                    <p className="truncate text-[10px] text-slate-600">
                      {agent.hostname} · {formatRelativeTime(agent.last_seen)}
                    </p>
                  </div>
                  <StatusBadge status={agent.status} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No host activity"
              description="Enrolled host check-ins will appear here."
            />
          )}
        </Card>
      </div>

      <ul className="sr-only">
        {metrics.agents_by_os.map((item) => (
          <li key={item.name}>
            {item.name}: {item.value} agents
          </li>
        ))}
        {metrics.agents_by_version.map((item) => (
          <li key={item.name}>
            {item.name}: {item.value} agents
          </li>
        ))}
      </ul>
    </div>
  );
}
