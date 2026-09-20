import type {
  Agent,
  AuditEvent,
  AuthTokens,
  DashboardActivity,
  DashboardMetrics,
  EnrollmentToken,
  AshborneSettings,
  AshborneTask,
  Paginated,
  Role,
  TaskType,
  User,
} from "../types";
import { tokenStore } from "./tokenStore";

const configuredBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
export const API_ROOT = `${configuredBase}/api/v1`;

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

let refreshPromise: Promise<string | null> | null = null;
let unauthorizedCallback: (() => void) | null = null;
let sessionUpdatedCallback: ((user: User) => void) | null = null;

export function onUnauthorized(callback: (() => void) | null) {
  unauthorizedCallback = callback;
}

export function onSessionUpdated(callback: ((user: User) => void) | null) {
  sessionUpdatedCallback = callback;
}

export function invalidateSession() {
  tokenStore.clear();
  unauthorizedCallback?.();
}

function query(
  params: Record<string, string | number | boolean | undefined | null>,
) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "")
      search.set(key, String(value));
  });
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

function paginated<T>(raw: any, normalize: (item: any) => T): Paginated<T> {
  const items = Array.isArray(raw?.items)
    ? raw.items
    : Array.isArray(raw)
      ? raw
      : [];
  return {
    items: items.map(normalize),
    total: Number(raw?.total ?? items.length),
    skip: Number(raw?.skip ?? 0),
    limit: Number(raw?.limit ?? items.length),
  };
}

export function normalizeTask(raw: any): AshborneTask {
  const requestedBy = raw?.requested_by;
  const requestedById =
    raw?.requested_by_id ??
    (typeof requestedBy === "object" ? requestedBy?.id : null);
  return {
    ...raw,
    id: String(raw?.id ?? raw?.task_id ?? ""),
    agent_id: String(raw?.agent_id ?? ""),
    task_type: raw?.task_type,
    status: raw?.status,
    requested_by_id: requestedById,
    requested_by: typeof requestedBy === "string" ? requestedBy : requestedById,
    requested_by_email:
      raw?.requested_by_email ??
      raw?.requesting_user_email ??
      (typeof requestedBy === "object" ? requestedBy?.email : null),
    created_at: raw?.created_at,
  } as AshborneTask;
}

function asArray<T>(value: unknown, keys: string[]): T[] | undefined {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    for (const key of keys) {
      const nested = (value as Record<string, unknown>)[key];
      if (Array.isArray(nested)) return nested as T[];
    }
  }
  return undefined;
}

function asRecord(value: unknown): Record<string, any> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : null;
}

function resultData(result: unknown): Record<string, any> | null {
  const envelope = asRecord(result);
  return asRecord(envelope?.data) ?? envelope;
}

function normalizeCpu(value: unknown): NonNullable<Agent["inventory"]>["cpu"] {
  const source = asRecord(value);
  if (!source) return undefined;
  return {
    model: source.model ?? source.processor,
    physical_cores: source.physical_cores,
    logical_cores: source.logical_cores,
    usage_percent: source.usage_percent ?? source.percent,
  };
}

function normalizeMemory(
  value: unknown,
): NonNullable<Agent["inventory"]>["memory"] {
  const source = asRecord(value);
  if (!source) return undefined;
  const physical =
    asRecord(source.physical) ?? asRecord(source.memory) ?? source;
  return {
    total_bytes: physical.total_bytes,
    available_bytes: physical.available_bytes ?? physical.free_bytes,
    used_percent: physical.used_percent ?? physical.percent,
  };
}

function normalizeDisks(
  value: unknown,
): NonNullable<Agent["inventory"]>["disks"] {
  const items = asArray<any>(value, ["disks", "partitions"]);
  return items?.map((item) => ({
    mountpoint: String(
      item?.mountpoint ?? item?.mount_point ?? item?.device ?? "Unknown",
    ),
    filesystem: item?.filesystem ?? item?.fstype,
    total_bytes: item?.total_bytes,
    free_bytes: item?.free_bytes ?? item?.available_bytes,
    used_percent: item?.used_percent ?? item?.percent,
  }));
}

function normalizeInterfaces(
  value: unknown,
): NonNullable<Agent["inventory"]>["interfaces"] {
  const items = asArray<any>(value, ["interfaces", "network_interfaces"]);
  return items?.map((item) => {
    const rawAddresses = Array.isArray(item?.addresses) ? item.addresses : [];
    const addresses = rawAddresses
      .map((address: any) =>
        typeof address === "string"
          ? address
          : address?.address == null
            ? null
            : String(address.address),
      )
      .filter((address: string | null): address is string => Boolean(address));
    const mac = rawAddresses.find(
      (address: any) =>
        typeof address === "object" &&
        String(address?.family ?? "").toUpperCase() === "MAC",
    );
    return {
      name: String(item?.name ?? "Unknown"),
      addresses,
      mac_address: item?.mac_address ?? mac?.address ?? null,
      is_up: item?.is_up,
    };
  });
}

function normalizeProcesses(
  value: unknown,
): NonNullable<Agent["inventory"]>["processes"] {
  const items = asArray<any>(value, ["processes"]);
  return items?.map((item) => ({
    pid: Number(item?.pid ?? 0),
    name: String(item?.name ?? "Unknown"),
    username: item?.username ?? null,
    cpu_percent: item?.cpu_percent ?? null,
    memory_percent: item?.memory_percent ?? null,
  }));
}

function normalizeListeningPorts(
  value: unknown,
): NonNullable<Agent["inventory"]>["listening_ports"] {
  const items = asArray<any>(value, ["listening_ports", "listeners", "ports"]);
  return items?.map((item) => ({
    protocol: String(
      item?.protocol ?? item?.transport ?? "unknown",
    ).toUpperCase(),
    address: String(item?.address ?? item?.local_address ?? ""),
    port: Number(item?.port ?? item?.local_port ?? 0),
    process: item?.process ?? item?.process_name ?? null,
    pid: item?.pid ?? null,
  }));
}

function normalizeInstalledSoftware(
  value: unknown,
): NonNullable<Agent["inventory"]>["installed_software"] {
  const items = asArray<any>(value, [
    "installed_software",
    "software",
    "packages",
  ]);
  return items?.map((item) => ({
    name: String(item?.name ?? "Unknown"),
    version: item?.version ?? null,
  }));
}

function normalizeInventory(value: unknown): Agent["inventory"] {
  const source = asRecord(value);
  if (!source) return null;
  const inventory: NonNullable<Agent["inventory"]> = {
    cpu: normalizeCpu(source.cpu),
    memory: normalizeMemory(source.memory),
    disks: normalizeDisks(source.disks ?? source.disk ?? source.partitions),
    interfaces: normalizeInterfaces(
      source.interfaces ?? source.network_interfaces,
    ),
    processes: normalizeProcesses(source.processes),
    listening_ports: normalizeListeningPorts(
      source.listening_ports ?? source.listeners ?? source.ports,
    ),
    installed_software: normalizeInstalledSoftware(
      source.installed_software ?? source.software ?? source.packages,
    ),
  };
  for (const key of Object.keys(inventory) as Array<keyof typeof inventory>) {
    if (inventory[key] === undefined) delete inventory[key];
  }
  return Object.keys(inventory).length ? inventory : null;
}

export function inventoryFromTasks(tasks: AshborneTask[]): Agent["inventory"] {
  const successful = [...tasks]
    .filter(
      (task) =>
        task.status === "SUCCESS" &&
        task.result &&
        typeof task.result === "object",
    )
    .sort(
      (a, b) =>
        new Date(b.completed_at ?? b.created_at).getTime() -
        new Date(a.completed_at ?? a.created_at).getTime(),
    );
  const inventory: NonNullable<Agent["inventory"]> = {};
  for (const task of successful) {
    const result = resultData(task.result);
    if (!result) continue;
    if (task.task_type === "SYSTEM_INFO") {
      const snapshot = normalizeInventory(result.inventory);
      inventory.cpu ??= snapshot?.cpu;
      inventory.memory ??= snapshot?.memory;
      inventory.disks ??= snapshot?.disks;
      inventory.interfaces ??= snapshot?.interfaces;
      inventory.processes ??= snapshot?.processes;
      inventory.listening_ports ??= snapshot?.listening_ports;
      inventory.installed_software ??= snapshot?.installed_software;
    }
    if (task.task_type === "CPU_INFO")
      inventory.cpu ??= normalizeCpu(result.cpu ?? result);
    if (task.task_type === "MEMORY_USAGE") {
      inventory.memory ??= normalizeMemory(result.memory ?? result);
    }
    if (task.task_type === "DISK_USAGE")
      inventory.disks ??= normalizeDisks(result);
    if (task.task_type === "NETWORK_INTERFACES") {
      inventory.interfaces ??= normalizeInterfaces(result);
    }
    if (task.task_type === "PROCESS_INVENTORY") {
      inventory.processes ??= normalizeProcesses(result);
    }
    if (task.task_type === "LISTENING_PORTS") {
      inventory.listening_ports ??= normalizeListeningPorts(result);
    }
    if (task.task_type === "INSTALLED_SOFTWARE") {
      inventory.installed_software ??= normalizeInstalledSoftware(result);
    }
  }
  return Object.keys(inventory).length ? inventory : null;
}

export function normalizeAgent(raw: any): Agent {
  const recentTasks = Array.isArray(raw?.recent_tasks)
    ? raw.recent_tasks.map(normalizeTask)
    : [];
  const heartbeatSource = Array.isArray(raw?.recent_heartbeats)
    ? raw.recent_heartbeats
    : Array.isArray(raw?.heartbeat_history)
      ? raw.heartbeat_history
      : [];
  return {
    ...raw,
    id: String(raw?.id ?? raw?.agent_id ?? ""),
    agent_id: String(raw?.agent_id ?? raw?.id ?? ""),
    uuid: String(raw?.uuid ?? raw?.agent_id ?? raw?.id ?? ""),
    name: String(raw?.name ?? raw?.hostname ?? "Unnamed agent"),
    hostname: String(raw?.hostname ?? "Unknown host"),
    operating_system: String(raw?.operating_system ?? raw?.os ?? "Unknown"),
    agent_version: String(raw?.agent_version ?? "Unknown"),
    tags: Array.isArray(raw?.tags) ? raw.tags : [],
    heartbeat_history: heartbeatSource.map((heartbeat: any) => ({
      ...heartbeat,
      timestamp:
        heartbeat.timestamp ?? heartbeat.received_at ?? heartbeat.reported_at,
      status: heartbeat.status ?? raw?.status,
    })),
    recent_tasks: recentTasks,
    inventory:
      normalizeInventory(raw?.inventory) ?? inventoryFromTasks(recentTasks),
  } as Agent;
}

function namedSeries(value: unknown): Array<{ name: string; value: number }> {
  if (Array.isArray(value))
    return value.map((item: any) => ({
      name: String(item.name ?? item.label ?? "Unknown"),
      value: Number(item.value ?? item.count ?? 0),
    }));
  if (value && typeof value === "object")
    return Object.entries(value).map(([name, count]) => ({
      name,
      value: Number(count),
    }));
  return [];
}

export function normalizeDashboardMetrics(raw: any): DashboardMetrics {
  const averageCheckIn =
    raw?.average_checkin_interval_seconds ?? raw?.average_check_in_seconds;
  return {
    total_agents: Number(raw?.total_agents ?? 0),
    online_agents: Number(raw?.online_agents ?? 0),
    degraded_agents: Number(raw?.degraded_agents ?? 0),
    offline_agents: Number(raw?.offline_agents ?? 0),
    tasks_queued: Number(raw?.tasks_queued ?? 0),
    tasks_running: Number(raw?.tasks_running ?? 0),
    tasks_completed: Number(raw?.tasks_completed ?? 0),
    tasks_failed: Number(raw?.tasks_failed ?? 0),
    task_success_rate: Number(raw?.task_success_rate ?? 0),
    average_check_in_seconds:
      averageCheckIn == null ? null : Number(averageCheckIn),
    agents_by_os: namedSeries(raw?.agents_by_os ?? raw?.os_distribution),
    agents_by_version: namedSeries(
      raw?.agents_by_version ?? raw?.version_distribution,
    ),
    tasks_over_time: (Array.isArray(raw?.tasks_over_time)
      ? raw.tasks_over_time
      : []
    ).map((item: any) => ({
      ...item,
      timestamp: item.timestamp ?? item.date,
      total: Number(item.total ?? item.created ?? 0),
      success: Number(item.success ?? 0),
      failed: Number(item.failed ?? 0),
    })),
    heartbeat_activity: (Array.isArray(raw?.heartbeat_activity)
      ? raw.heartbeat_activity
      : []
    ).map((item: any) => ({
      ...item,
      timestamp: item.timestamp ?? item.date,
      count: Number(item.count ?? 0),
    })),
  };
}

export function normalizeDashboardActivity(raw: any): DashboardActivity {
  return {
    latest_agents: (Array.isArray(raw?.latest_agents)
      ? raw.latest_agents
      : Array.isArray(raw?.agents)
        ? raw.agents
        : []
    ).map(normalizeAgent),
    recent_tasks: (Array.isArray(raw?.recent_tasks)
      ? raw.recent_tasks
      : Array.isArray(raw?.tasks)
        ? raw.tasks
        : []
    ).map(normalizeTask),
    audit_events: Array.isArray(raw?.audit_events) ? raw.audit_events : [],
  };
}

async function readBody(response: Response) {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return response.json();
  const text = await response.text();
  return text || undefined;
}

function errorMessage(body: any, fallback: string) {
  if (typeof body === "string") return body;
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail))
    return (
      body.detail
        .map((item: any) => item.msg)
        .filter(Boolean)
        .join(", ") || fallback
    );
  if (typeof body?.message === "string") return body.message;
  return fallback;
}

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) return null;
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_ROOT}/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const body = (await response.json()) as Partial<AuthTokens>;
        if (!body.access_token) return null;
        tokenStore.set(body.access_token, body.refresh_token ?? refreshToken);
        if (body.user?.id) sessionUpdatedCallback?.(body.user);
        return body.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  auth?: boolean;
  retry?: boolean;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, auth = true, retry = true, headers, ...init } = options;
  const accessToken = tokenStore.getAccess();
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(auth && accessToken
        ? { Authorization: `Bearer ${accessToken}` }
        : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (response.status === 401 && auth && retry) {
    const newToken = await refreshAccessToken();
    if (newToken) return request<T>(path, { ...options, retry: false });
    invalidateSession();
  }

  const responseBody = await readBody(response);
  if (!response.ok) {
    throw new ApiError(
      errorMessage(responseBody, `Request failed (${response.status})`),
      response.status,
      responseBody,
    );
  }
  return responseBody as T;
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      request<AuthTokens>("/auth/login", {
        method: "POST",
        auth: false,
        body: { email, password },
      }),
    refresh: refreshAccessToken,
    me: () => request<User>("/auth/me"),
    logout: (refreshToken: string | null) =>
      request<void>("/auth/logout", {
        method: "POST",
        body: { refresh_token: refreshToken },
        retry: false,
      }),
  },
  dashboard: {
    metrics: () =>
      request<any>("/dashboard/metrics").then(normalizeDashboardMetrics),
    activity: () =>
      request<any>("/dashboard/activity").then(normalizeDashboardActivity),
  },
  agents: {
    list: (params: {
      search?: string;
      status?: string;
      tag?: string;
      sort_by?: string;
      sort_order?: string;
      skip?: number;
      limit?: number;
    }) =>
      request<any>(`/agents${query(params)}`).then((value) =>
        paginated(value, normalizeAgent),
      ),
    get: (id: string) =>
      request<any>(`/agents/${encodeURIComponent(id)}`).then(normalizeAgent),
    remove: (id: string) =>
      request<void>(`/agents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  },
  tasks: {
    list: (params: {
      search?: string;
      status?: string;
      task_type?: string;
      agent_id?: string;
      skip?: number;
      limit?: number;
    }) =>
      request<any>(`/tasks${query(params)}`).then((value) =>
        paginated(value, normalizeTask),
      ),
    get: (id: string) =>
      request<any>(`/tasks/${encodeURIComponent(id)}`).then(normalizeTask),
    create: (
      agentId: string,
      taskType: TaskType,
      authorizedScopeConfirmed: boolean,
    ) =>
      request<any>("/tasks", {
        method: "POST",
        body: {
          agent_id: agentId,
          task_type: taskType,
          parameters: {},
          authorized_scope_confirmed: authorizedScopeConfirmed,
        },
      }).then(normalizeTask),
    cancel: (id: string) =>
      request<any>(`/tasks/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      }).then(normalizeTask),
  },
  audit: {
    list: (params: {
      search?: string;
      user?: string;
      agent?: string;
      event_type?: string;
      source_ip?: string;
      start_time?: string;
      end_time?: string;
      skip?: number;
      limit?: number;
    }) => request<Paginated<AuditEvent>>(`/audit${query(params)}`),
    eventTypes: () => request<string[]>("/audit/event-types"),
  },
  users: {
    list: (params: {
      search?: string;
      role?: string;
      skip?: number;
      limit?: number;
    }) => request<Paginated<User>>(`/users${query(params)}`),
    create: (payload: {
      email: string;
      display_name: string;
      password: string;
      role: Role;
    }) => request<User>("/users", { method: "POST", body: payload }),
    update: (
      id: string,
      payload: Partial<Pick<User, "display_name" | "role" | "is_active">>,
    ) =>
      request<User>(`/users/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: payload,
      }),
    remove: (id: string) =>
      request<void>(`/users/${encodeURIComponent(id)}`, { method: "DELETE" }),
  },
  settings: {
    get: () => request<AshborneSettings>("/settings"),
    update: (payload: AshborneSettings) =>
      request<AshborneSettings>("/settings", {
        method: "PATCH",
        body: payload,
      }),
  },
  enrollment: {
    list: () => request<Paginated<EnrollmentToken>>("/enrollment/tokens"),
    create: (payload: { expires_in_seconds: number; description?: string }) =>
      request<EnrollmentToken>("/enrollment/tokens", {
        method: "POST",
        body: payload,
      }),
    revoke: (id: string) =>
      request<void>(`/enrollment/tokens/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
  },
};
