export const ROLES = ["ADMINISTRATOR", "OPERATOR", "VIEWER"] as const;
export type Role = (typeof ROLES)[number];

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export const AGENT_STATUSES = ["ONLINE", "DEGRADED", "OFFLINE"] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];

export interface NetworkInterface {
  name: string;
  addresses?: string[];
  mac_address?: string | null;
  is_up?: boolean;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  username?: string | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
}

export interface ListeningPort {
  protocol: string;
  address: string;
  port: number;
  process?: string | null;
  pid?: number | null;
}

export interface AgentInventory {
  cpu?: {
    model?: string;
    physical_cores?: number;
    logical_cores?: number;
    usage_percent?: number;
  };
  memory?: {
    total_bytes?: number;
    available_bytes?: number;
    used_percent?: number;
  };
  disks?: Array<{
    mountpoint: string;
    filesystem?: string;
    total_bytes?: number;
    free_bytes?: number;
    used_percent?: number;
  }>;
  interfaces?: NetworkInterface[];
  processes?: ProcessInfo[];
  listening_ports?: ListeningPort[];
  installed_software?: Array<{ name: string; version?: string | null }>;
}

export interface Heartbeat {
  id?: string;
  timestamp: string;
  status?: AgentStatus;
  uptime_seconds?: number;
  agent_version?: string;
}

export interface Agent {
  id: string;
  agent_id?: string;
  uuid?: string;
  name: string;
  hostname: string;
  username?: string | null;
  operating_system: string;
  os_version?: string | null;
  architecture?: string | null;
  ip_address?: string | null;
  agent_version: string;
  first_seen: string;
  last_seen: string | null;
  status: AgentStatus;
  tags: string[];
  uptime_seconds?: number | null;
  inventory?: AgentInventory | null;
  heartbeat_history?: Heartbeat[];
  recent_tasks?: AshborneTask[];
}

export const TASK_TYPES = [
  "QUICK_RECON",
  "SYSTEM_INFO",
  "HOSTNAME",
  "CURRENT_USER",
  "SECURITY_CONTEXT",
  "CPU_INFO",
  "MEMORY_USAGE",
  "DISK_USAGE",
  "FILE_SYSTEM_OVERVIEW",
  "NETWORK_INTERFACES",
  "NETWORK_CONNECTIONS",
  "ROUTE_TABLE",
  "UPTIME",
  "PROCESS_INVENTORY",
  "INSTALLED_SOFTWARE",
  "LISTENING_PORTS",
  "AGENT_HEALTH",
  "PING",
  "LINUX_KERNEL_INFO",
  "LINUX_IDENTITY",
  "GROUP_MEMBERSHIP",
  "LINUX_CAPABILITIES",
  "LINUX_MOUNTS",
  "SAFE_ENVIRONMENT_OVERVIEW",
  "SERVICE_OVERVIEW",
  "SCHEDULED_ACTIVITY_OVERVIEW",
  "PRIVILEGE_ENUMERATION",
  "NETWORK_OVERVIEW",
  "HOST_RECON",
] as const;
export type TaskType = (typeof TASK_TYPES)[number];

export const TASK_CATEGORIES = {
  Recon: [
    "QUICK_RECON",
    "HOST_RECON",
    "SYSTEM_INFO",
    "HOSTNAME",
    "CURRENT_USER",
    "UPTIME",
  ],
  "Host Enumeration": [
    "CPU_INFO",
    "MEMORY_USAGE",
    "DISK_USAGE",
    "PROCESS_INVENTORY",
    "INSTALLED_SOFTWARE",
    "LINUX_KERNEL_INFO",
    "SERVICE_OVERVIEW",
    "SCHEDULED_ACTIVITY_OVERVIEW",
  ],
  "Privilege Enumeration": [
    "SECURITY_CONTEXT",
    "LINUX_IDENTITY",
    "GROUP_MEMBERSHIP",
    "LINUX_CAPABILITIES",
    "PRIVILEGE_ENUMERATION",
  ],
  Files: [
    "FILE_SYSTEM_OVERVIEW",
    "LINUX_MOUNTS",
    "SAFE_ENVIRONMENT_OVERVIEW",
  ],
  Network: [
    "NETWORK_INTERFACES",
    "NETWORK_CONNECTIONS",
    "ROUTE_TABLE",
    "LISTENING_PORTS",
    "NETWORK_OVERVIEW",
  ],
  "Agent Control": ["AGENT_HEALTH", "PING"],
} as const satisfies Record<string, readonly TaskType[]>;
export type TaskCategory = keyof typeof TASK_CATEGORIES;

export const TASK_DESCRIPTIONS: Record<TaskType, string> = {
  QUICK_RECON: "Collect a bounded, passive local-host baseline in one action.",
  SYSTEM_INFO:
    "Report operating system, kernel, architecture, and agent details.",
  HOSTNAME: "Return the enrolled host name.",
  CURRENT_USER: "Return the local identity running the agent.",
  SECURITY_CONTEXT:
    "Report elevation state, local IDs, groups, and sandbox controls.",
  CPU_INFO: "Summarize processor capacity and current utilization.",
  MEMORY_USAGE: "Summarize physical and swap memory utilization.",
  DISK_USAGE: "Summarize mounted volume capacity.",
  FILE_SYSTEM_OVERVIEW:
    "Inspect fixed location metadata without reading file contents.",
  NETWORK_INTERFACES: "List local interfaces and numeric addresses.",
  NETWORK_CONNECTIONS:
    "List bounded local socket state without DNS resolution.",
  ROUTE_TABLE:
    "Read the local route table where the platform exposes it safely.",
  UPTIME: "Report boot time and uptime.",
  PROCESS_INVENTORY: "List a bounded process inventory without command lines.",
  INSTALLED_SOFTWARE: "List a bounded installed-software inventory.",
  LISTENING_PORTS: "List local listening TCP and UDP endpoints.",
  AGENT_HEALTH: "Report agent resource health and runtime state.",
  PING: "Verify the authenticated task round trip.",
  LINUX_KERNEL_INFO: "Report bounded local kernel and platform metadata.",
  LINUX_IDENTITY: "Report local numeric identity and account metadata.",
  GROUP_MEMBERSHIP: "List bounded local group membership for the agent identity.",
  LINUX_CAPABILITIES: "Report local Linux capability masks without changing them.",
  LINUX_MOUNTS: "List bounded local mount metadata without reading file contents.",
  SAFE_ENVIRONMENT_OVERVIEW:
    "List safe environment variable names while filtering secret-bearing names and all values.",
  SERVICE_OVERVIEW: "List bounded local service state without controlling services.",
  SCHEDULED_ACTIVITY_OVERVIEW:
    "Summarize bounded scheduled-activity metadata without modifying jobs.",
  PRIVILEGE_ENUMERATION:
    "Combine read-only local identity, group, and capability observations.",
  NETWORK_OVERVIEW:
    "Combine bounded interface, route, listener, and connection observations.",
  HOST_RECON: "Collect a bounded host-focused lab reconnaissance summary.",
};

export const TASK_CATEGORY_BY_TYPE = Object.fromEntries(
  Object.entries(TASK_CATEGORIES).flatMap(([category, taskTypes]) =>
    taskTypes.map((taskType) => [taskType, category]),
  ),
) as Record<TaskType, TaskCategory>;

export const TASK_STATUSES = [
  "QUEUED",
  "DISPATCHED",
  "RUNNING",
  "SUCCESS",
  "FAILED",
  "CANCELLED",
  "EXPIRED",
] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

export interface AshborneTask {
  id: string;
  agent_id: string;
  agent_name?: string | null;
  task_type: TaskType;
  parameters?: Record<string, unknown>;
  requested_by?: string | null;
  requested_by_email?: string | null;
  requested_by_id?: string | null;
  created_at: string;
  dispatched_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  status: TaskStatus;
  result?: unknown;
  error_message?: string | null;
  bulk_operation_id?: string | null;
  audit_events?: AuditEvent[];
}

export interface BulkOperationSummary {
  bulk_operation_id: string;
  task_type: TaskType;
  parameters: Record<string, unknown>;
  requested_by_id?: string | null;
  requested_by?: string | null;
  requested_by_email?: string | null;
  created_at: string;
  target_count: number;
  status_counts: Record<TaskStatus, number>;
}

export interface BulkOperation extends BulkOperationSummary {
  tasks: AshborneTask[];
}

export const AUDIT_EVENT_TYPES = [
  "USER_LOGIN_SUCCESS",
  "USER_LOGIN_FAILURE",
  "USER_CREATED",
  "USER_ROLE_CHANGED",
  "AGENT_ENROLLED",
  "AGENT_REMOVED",
  "AGENT_HEARTBEAT",
  "ENROLLMENT_TOKEN_CREATED",
  "TASK_CREATED",
  "TASK_DISPATCHED",
  "TASK_STARTED",
  "TASK_COMPLETED",
  "TASK_FAILED",
] as const;
export type AuditEventType = (typeof AUDIT_EVENT_TYPES)[number] | string;

export interface AuditEvent {
  id: string;
  event_type: AuditEventType;
  timestamp: string;
  user_id?: string | null;
  user_email?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  source_ip?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface DashboardMetrics {
  total_agents: number;
  online_agents: number;
  degraded_agents: number;
  offline_agents: number;
  tasks_queued: number;
  tasks_running: number;
  tasks_completed: number;
  tasks_failed: number;
  task_success_rate: number;
  average_check_in_seconds: number | null;
  agents_by_os: Array<{ name: string; value: number }>;
  agents_by_version: Array<{ name: string; value: number }>;
  tasks_over_time: Array<{
    timestamp: string;
    success: number;
    failed: number;
    total?: number;
  }>;
  heartbeat_activity: Array<{ timestamp: string; count: number }>;
}

export interface DashboardActivity {
  latest_agents: Agent[];
  recent_tasks: AshborneTask[];
  audit_events: AuditEvent[];
}

export interface AshborneSettings {
  heartbeat_interval_seconds: number;
  degraded_threshold_seconds: number;
  offline_threshold_seconds: number;
  task_expiration_seconds: number;
  session_timeout_minutes: number;
  page_size: number;
  audit_retention_days: number;
}

export interface EnrollmentToken {
  id: string;
  prefix: string;
  token?: string;
  description?: string | null;
  created_by_id: string;
  created_at: string;
  expires_at: string;
  used_at?: string | null;
  used_by_agent_id?: string | null;
  revoked_at?: string | null;
}

export interface LiveEvent<T = unknown> {
  type: string;
  timestamp?: string;
  data: T;
}
