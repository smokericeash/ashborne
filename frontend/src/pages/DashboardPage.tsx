import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  RadioTower,
  ShieldCheck,
  ShieldEllipsis,
  ShieldOff,
  Siren,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionTitle,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useLive } from "../context/useLive";
import { formatDuration, formatRelativeTime, humanize } from "../lib/utils";
import { api } from "../services/api";
import { useResource } from "../hooks/useResource";
import type { DashboardActivity, DashboardMetrics } from "../types";

const STATUS_COLORS = ["#25cfbe", "#f2b84b", "#f05d66"];

const emptyMetrics: DashboardMetrics = {
  total_agents: 0,
  online_agents: 0,
  degraded_agents: 0,
  offline_agents: 0,
  tasks_queued: 0,
  tasks_running: 0,
  tasks_completed: 0,
  tasks_failed: 0,
  task_success_rate: 0,
  average_check_in_seconds: null,
  agents_by_os: [],
  agents_by_version: [],
  tasks_over_time: [],
  heartbeat_activity: [],
};

const emptyActivity: DashboardActivity = {
  latest_agents: [],
  recent_tasks: [],
  audit_events: [],
};

function formatBucketDate(value: string) {
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value}T00:00:00`
    : value;
  return new Date(normalized).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function Tick({ x, y, payload }: any) {
  return (
    <text x={x} y={y + 11} textAnchor="middle" fill="#64748b" fontSize="10">
      {payload.value}
    </text>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-obsidian/95 px-3 py-2 shadow-2xl">
      <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </p>
      {payload.map((item: any) => (
        <p
          key={item.dataKey ?? item.name}
          className="text-xs"
          style={{ color: item.color }}
        >
          {humanize(String(item.name))}: {Number(item.value).toLocaleString()}
        </p>
      ))}
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "cyan",
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: typeof ShieldCheck;
  tone?: "cyan" | "green" | "amber" | "red";
}) {
  const tones = {
    cyan: "border-cyan-500/20 bg-cyan-500/[.07] text-cyan-300",
    green: "border-emerald-500/20 bg-emerald-500/[.07] text-emerald-300",
    amber: "border-amber-500/20 bg-amber-500/[.07] text-amber-300",
    red: "border-red-500/20 bg-red-500/[.07] text-red-300",
  };
  return (
    <Card className="group relative overflow-hidden p-4 transition hover:-translate-y-0.5 hover:border-slate-600/60">
      <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-ashborne-400/[.025] blur-2xl transition group-hover:bg-ashborne-400/[.06]" />
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[.13em] text-slate-500">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-50">
            {value}
          </p>
        </div>
        <div
          className={`grid h-9 w-9 place-items-center rounded-lg border ${tones[tone]}`}
        >
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <p className="mt-2 text-[11px] text-slate-600">{detail}</p>
    </Card>
  );
}

export function DashboardPage() {
  const { revision, connected } = useLive();
  const resource = useResource(async () => {
    const [metrics, activity] = await Promise.all([
      api.dashboard.metrics(),
      api.dashboard.activity(),
    ]);
    return { metrics, activity };
  }, [revision]);

  if (resource.loading)
    return (
      <>
        <PageHeader
          eyebrow="Authorized operation"
          title="Command center"
          description="Live lab-host posture, typed task execution, and operator accountability."
        />
        <Spinner label="Synchronizing lab state" />
      </>
    );
  if (resource.error && !resource.data)
    return (
      <>
        <PageHeader eyebrow="Authorized operation" title="Command center" />
        <Card>
          <ErrorState
            error={resource.error}
            onRetry={() => void resource.reload()}
          />
        </Card>
      </>
    );

  const metrics = resource.data?.metrics ?? emptyMetrics;
  const activity = resource.data?.activity ?? emptyActivity;
  const agentStatuses = [
    { name: "Online", value: metrics.online_agents },
    { name: "Degraded", value: metrics.degraded_agents },
    { name: "Offline", value: metrics.offline_agents },
  ];

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Authorized operation"
        title="Command center"
        description="Live lab-host posture, typed task execution, and operator accountability."
        actions={
          <div className="flex items-center gap-2 rounded-lg border border-line bg-panel/70 px-3 py-2 text-[10px] font-semibold uppercase tracking-[.12em] text-slate-500">
            <span
              className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-slate-600"}`}
            />
            {connected ? "Stream connected" : "Stream reconnecting"}
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Lab hosts"
          value={metrics.total_agents}
          detail={`${metrics.online_agents} currently reporting`}
          icon={ShieldCheck}
        />
        <MetricCard
          label="Online"
          value={metrics.online_agents}
          detail="Within heartbeat threshold"
          icon={RadioTower}
          tone="green"
        />
        <MetricCard
          label="Degraded"
          value={metrics.degraded_agents}
          detail="Check-in delayed"
          icon={ShieldEllipsis}
          tone="amber"
        />
        <MetricCard
          label="Offline"
          value={metrics.offline_agents}
          detail="Beyond offline threshold"
          icon={ShieldOff}
          tone="red"
        />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Queued tasks"
          value={metrics.tasks_queued}
          detail={`${metrics.tasks_running} currently running`}
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Completed"
          value={metrics.tasks_completed}
          detail="Successful and failed terminal tasks"
          icon={CheckCircle2}
          tone="green"
        />
        <MetricCard
          label="Failed"
          value={metrics.tasks_failed}
          detail="Review task results"
          icon={Siren}
          tone="red"
        />
        <MetricCard
          label="Success rate"
          value={`${Number(metrics.task_success_rate || 0).toFixed(1)}%`}
          detail={`Avg check-in ${formatDuration(metrics.average_check_in_seconds)}`}
          icon={Activity}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[.82fr_1.18fr]">
        <Card className="min-w-0 overflow-hidden">
          <SectionTitle
            title="Lab-host posture"
            description="Current heartbeat-derived status"
          />
          <div className="grid h-[290px] grid-cols-[1fr_130px] items-center p-4">
            {metrics.total_agents ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={agentStatuses}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="62%"
                    outerRadius="88%"
                    paddingAngle={3}
                    stroke="transparent"
                  >
                    {agentStatuses.map((entry, index) => (
                      <Cell key={entry.name} fill={STATUS_COLORS[index]} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                  <text
                    x="50%"
                    y="47%"
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="#fff"
                    fontSize="28"
                    fontWeight="600"
                  >
                    {metrics.total_agents}
                  </text>
                  <text
                    x="50%"
                    y="58%"
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="#64748b"
                    fontSize="9"
                  >
                    ENROLLED
                  </text>
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                title="No lab hosts yet"
                description="Enroll a lab host to populate its posture view."
              />
            )}
            <div className="space-y-4">
              {agentStatuses.map((item, index) => (
                <div key={item.name}>
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: STATUS_COLORS[index] }}
                    />
                    {item.name}
                  </div>
                  <p className="mt-1 pl-3.5 text-lg font-semibold text-slate-200">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <SectionTitle
            title="Task outcome trend"
            description="Success and failure volume over time"
          />
          <div className="h-[290px] p-4 pt-6">
            {metrics.tasks_over_time.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={metrics.tasks_over_time}
                  margin={{ left: -25, right: 8, top: 8 }}
                >
                  <defs>
                    <linearGradient
                      id="successGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0" stopColor="#25cfbe" stopOpacity={0.35} />
                      <stop offset="1" stopColor="#25cfbe" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient
                      id="failedGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0" stopColor="#f05d66" stopOpacity={0.22} />
                      <stop offset="1" stopColor="#f05d66" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    vertical={false}
                    stroke="#1b2633"
                    strokeDasharray="3 5"
                  />
                  <XAxis
                    dataKey="timestamp"
                    tick={<Tick />}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={formatBucketDate}
                  />
                  <YAxis
                    tick={{ fill: "#64748b", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="success"
                    stroke="#25cfbe"
                    strokeWidth={2}
                    fill="url(#successGradient)"
                  />
                  <Area
                    type="monotone"
                    dataKey="failed"
                    stroke="#f05d66"
                    strokeWidth={1.5}
                    fill="url(#failedGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                title="No task history"
                description="Completed tasks will form an outcome trend here."
              />
            )}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="min-w-0 overflow-hidden">
          <SectionTitle
            title="Operating systems"
            description="Enrolled lab-host distribution"
          />
          <div className="h-64 p-4">
            {metrics.agents_by_os.length ? (
              <>
                <ul className="sr-only">
                  {metrics.agents_by_os.map((item) => (
                    <li key={item.name}>
                      {item.name}: {item.value} agents
                    </li>
                  ))}
                </ul>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={metrics.agents_by_os}
                    layout="vertical"
                    margin={{ left: 5, right: 20 }}
                  >
                    <CartesianGrid
                      horizontal={false}
                      stroke="#1b2633"
                      strokeDasharray="3 5"
                    />
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={90}
                      tick={{ fill: "#94a3b8", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      content={<ChartTooltip />}
                      cursor={{ fill: "rgba(255,255,255,.025)" }}
                    />
                    <Bar
                      dataKey="value"
                      name="Agents"
                      fill="#25cfbe"
                      radius={[0, 4, 4, 0]}
                      barSize={12}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </>
            ) : (
              <EmptyState
                title="No OS inventory"
                description="Distribution appears as agents report inventory."
              />
            )}
          </div>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <SectionTitle
            title="Agent versions"
            description="Deployed agent release distribution"
          />
          <div className="h-64 p-4">
            {metrics.agents_by_version.length ? (
              <>
                <ul className="sr-only">
                  {metrics.agents_by_version.map((item) => (
                    <li key={item.name}>
                      {item.name}: {item.value} agents
                    </li>
                  ))}
                </ul>
                <BarChartPanel data={metrics.agents_by_version} />
              </>
            ) : (
              <EmptyState
                title="No version inventory"
                description="Version distribution appears as agents report."
              />
            )}
          </div>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <SectionTitle
            title="Heartbeat activity"
            description="Check-ins observed over time"
          />
          <div className="h-64 p-4 pt-6">
            {metrics.heartbeat_activity.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={metrics.heartbeat_activity}
                  margin={{ left: -25, right: 10 }}
                >
                  <defs>
                    <linearGradient
                      id="heartbeatGradient"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0" stopColor="#38bdf8" stopOpacity={0.3} />
                      <stop offset="1" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    vertical={false}
                    stroke="#1b2633"
                    strokeDasharray="3 5"
                  />
                  <XAxis
                    dataKey="timestamp"
                    tick={<Tick />}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={formatBucketDate}
                  />
                  <YAxis
                    tick={{ fill: "#64748b", fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="count"
                    name="Heartbeats"
                    stroke="#38bdf8"
                    strokeWidth={2}
                    fill="url(#heartbeatGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                title="No heartbeat series"
                description="Live check-in activity will appear here."
              />
            )}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card className="overflow-hidden">
          <SectionTitle
            title="Latest lab-host activity"
            action={
              <Link
                className="flex items-center gap-1 text-[11px] font-semibold text-ashborne-400 hover:text-ashborne-300"
                to="/agents"
              >
                All lab hosts <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
          {activity.latest_agents.length ? (
            <div className="divide-y divide-line/60">
              {activity.latest_agents.slice(0, 6).map((agent) => (
                <Link
                  key={agent.id}
                  to={`/agents/${agent.id}`}
                  className="flex items-center gap-3 px-5 py-3.5 transition hover:bg-white/[.025]"
                >
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-void">
                    <ShieldCheck className="h-4 w-4 text-slate-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-200">
                      {agent.name || agent.hostname}
                    </p>
                    <p className="truncate text-[11px] text-slate-600">
                      {agent.hostname} · {agent.operating_system}
                    </p>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={agent.status} />
                    <p className="mt-1 text-[10px] text-slate-600">
                      {formatRelativeTime(agent.last_seen)}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No lab-host activity"
              description="New enrollments and heartbeats will be shown here."
            />
          )}
        </Card>

        <Card className="overflow-hidden">
          <SectionTitle
            title="Recent task activity"
            action={
              <Link
                className="flex items-center gap-1 text-[11px] font-semibold text-ashborne-400 hover:text-ashborne-300"
                to="/tasks"
              >
                All tasks <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
          {activity.recent_tasks.length ? (
            <div className="divide-y divide-line/60">
              {activity.recent_tasks.slice(0, 6).map((task) => (
                <Link
                  key={task.id}
                  to={`/tasks?focus=${task.id}`}
                  className="flex items-center gap-3 px-5 py-3.5 transition hover:bg-white/[.025]"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-slate-200">
                      {task.task_type}
                    </p>
                    <p className="truncate text-[11px] text-slate-600">
                      {task.agent_name || task.agent_id}
                    </p>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={task.status} />
                    <p className="mt-1 text-[10px] text-slate-600">
                      {formatRelativeTime(task.created_at)}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No recent tasks"
              description="Authorized typed lab actions will appear here."
            />
          )}
        </Card>
      </div>
    </div>
  );
}

function BarChartPanel({
  data,
}: {
  data: Array<{ name: string; value: number }>;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ left: 5, right: 20 }}>
        <CartesianGrid
          horizontal={false}
          stroke="#1b2633"
          strokeDasharray="3 5"
        />
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={90}
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: "rgba(255,255,255,.025)" }}
        />
        <Bar
          dataKey="value"
          name="Agents"
          fill="#8b5cf6"
          radius={[0, 4, 4, 0]}
          barSize={12}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
