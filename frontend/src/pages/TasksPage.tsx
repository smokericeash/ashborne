import { Ban, ClipboardList, Search, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useAuth } from "../context/useAuth";
import { useLive } from "../context/useLive";
import { useToast } from "../context/useToast";
import { useResource } from "../hooks/useResource";
import {
  canIssueTasks,
  formatDate,
  formatDuration,
  humanize,
} from "../lib/utils";
import { api } from "../services/api";
import {
  TASK_CATEGORIES,
  TASK_CATEGORY_BY_TYPE,
  TASK_STATUSES,
  type AshborneTask,
} from "../types";

function taskDuration(task: AshborneTask) {
  if (!task.started_at) return "—";
  const end = task.completed_at
    ? new Date(task.completed_at).getTime()
    : Date.now();
  return formatDuration(
    Math.max(0, (end - new Date(task.started_at).getTime()) / 1000),
  );
}

export function TasksPage() {
  const { user } = useAuth();
  const { revision } = useLive();
  const { notify } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [taskType, setTaskType] = useState("");
  const [skip, setSkip] = useState(0);
  const [selected, setSelected] = useState<AshborneTask | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const resource = useResource(
    () => api.tasks.list({ search, status, task_type: taskType, skip }),
    [search, status, taskType, skip, revision],
  );

  useEffect(() => {
    const focus = searchParams.get("focus");
    if (!focus) return;
    const existing = resource.data?.items.find((task) => task.id === focus);
    if (existing) setSelected(existing);
    else
      api.tasks
        .get(focus)
        .then(setSelected)
        .catch(() => undefined);
    setSearchParams(
      (current) => {
        current.delete("focus");
        return current;
      },
      { replace: true },
    );
  }, [resource.data, searchParams, setSearchParams]);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setSearch(draftSearch.trim());
    setSkip(0);
  };

  const cancelTask = async () => {
    if (!selected) return;
    setCancelling(true);
    try {
      const updated = await api.tasks.cancel(selected.id);
      setSelected(updated);
      notify("Task cancelled.");
      void resource.reload();
    } catch (caught) {
      notify(
        caught instanceof Error
          ? caught.message
          : "Task could not be cancelled.",
        "error",
      );
    } finally {
      setCancelling(false);
    }
  };

  const hasFilters = Boolean(search || status || taskType);
  const clearFilters = () => {
    setDraftSearch("");
    setSearch("");
    setStatus("");
    setTaskType("");
    setSkip(0);
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Operator dispatch ledger"
        title="Tasks"
        description="Track every authorized, typed lab action from request through structured result."
      />
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line/70 p-4 xl:flex-row">
          <form className="relative flex-1 xl:max-w-md" onSubmit={submitSearch}>
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-600" />
            <Input
              aria-label="Search tasks"
              className="pl-9 pr-9"
              placeholder="Search task, agent, operator, or UUID…"
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
            />
            {draftSearch && (
              <button
                type="button"
                aria-label="Clear task search"
                className="absolute right-2 top-2 grid h-6 w-6 place-items-center text-slate-600"
                onClick={() => {
                  setDraftSearch("");
                  setSearch("");
                }}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </form>
          <div className="grid gap-2 sm:grid-cols-3 xl:flex">
            <Select
              aria-label="Task status"
              className="xl:w-40"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setSkip(0);
              }}
            >
              <option value="">All statuses</option>
              {TASK_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Task type"
              className="xl:w-52"
              value={taskType}
              onChange={(event) => {
                setTaskType(event.target.value);
                setSkip(0);
              }}
            >
              <option value="">All task types</option>
              {Object.entries(TASK_CATEGORIES).map(([category, taskTypes]) => (
                <optgroup key={category} label={category}>
                  {taskTypes.map((item) => (
                    <option key={item} value={item}>
                      {humanize(item)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            {hasFilters && (
              <Button variant="ghost" onClick={clearFilters}>
                Clear filters
              </Button>
            )}
          </div>
        </div>

        {resource.loading ? (
          <Spinner label="Loading dispatch ledger" />
        ) : resource.error && !resource.data ? (
          <ErrorState
            error={resource.error}
            onRetry={() => void resource.reload()}
          />
        ) : resource.data?.items.length ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full" aria-label="ASHBORNE tasks">
                <thead className="border-b border-line/70 bg-void/25">
                  <tr>
                    <th className="table-heading">Lab action</th>
                    <th className="table-heading">Target host</th>
                    <th className="table-heading">Requested by</th>
                    <th className="table-heading">Created</th>
                    <th className="table-heading">Duration</th>
                    <th className="table-heading">Status</th>
                    <th className="table-heading">
                      <span className="sr-only">Action</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/50">
                  {resource.data.items.map((task) => (
                    <tr
                      key={task.id}
                      className="transition hover:bg-white/[.025]"
                    >
                      <td className="table-cell">
                        <p className="font-mono text-xs font-medium text-slate-200">
                          {task.task_type}
                        </p>
                        <Badge className="mt-1">
                          {TASK_CATEGORY_BY_TYPE[task.task_type]}
                        </Badge>
                        <p className="mt-1 max-w-40 truncate font-mono text-[9px] text-slate-700">
                          {task.id}
                        </p>
                      </td>
                      <td className="table-cell">
                        <Link
                          className="text-slate-300 hover:text-ashborne-300"
                          to={`/agents/${task.agent_id}`}
                        >
                          {task.agent_name || task.agent_id}
                        </Link>
                      </td>
                      <td className="table-cell">
                        {task.requested_by_email ||
                          task.requested_by ||
                          "System"}
                      </td>
                      <td className="table-cell">
                        {formatDate(task.created_at)}
                      </td>
                      <td className="table-cell font-mono text-xs">
                        {taskDuration(task)}
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={task.status} />
                      </td>
                      <td className="table-cell text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setSelected(task)}
                        >
                          Inspect
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              skip={resource.data.skip}
              limit={resource.data.limit}
              total={resource.data.total}
              onChange={setSkip}
            />
          </>
        ) : (
          <EmptyState
            title="No tasks match"
            description={
              hasFilters
                ? "Adjust or clear the active task filters."
                : "Authorized lab actions issued from a host detail page will appear here."
            }
            icon={<ClipboardList className="h-5 w-5" />}
          />
        )}
      </Card>

      <Modal
        open={Boolean(selected)}
        title={selected ? humanize(selected.task_type) : "Task detail"}
        description={selected?.id}
        onClose={() => setSelected(null)}
        width="max-w-2xl"
      >
        {selected && (
          <div className="p-5">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-line bg-void/40 p-3">
                <p className="text-[9px] uppercase tracking-wider text-slate-600">
                  Status
                </p>
                <div className="mt-2">
                  <StatusBadge status={selected.status} />
                </div>
              </div>
              <div className="rounded-lg border border-line bg-void/40 p-3">
                <p className="text-[9px] uppercase tracking-wider text-slate-600">
                  Duration
                </p>
                <p className="mt-2 font-mono text-sm text-slate-200">
                  {taskDuration(selected)}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-void/40 p-3">
                <p className="text-[9px] uppercase tracking-wider text-slate-600">
                  Requested by
                </p>
                <p className="mt-2 truncate text-sm text-slate-200">
                  {selected.requested_by_email ||
                    selected.requested_by ||
                    "System"}
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
              <Badge>{humanize(selected.task_type)}</Badge>
              <Badge tone="danger">
                {TASK_CATEGORY_BY_TYPE[selected.task_type]}
              </Badge>
              <span>Created {formatDate(selected.created_at)}</span>
              {selected.completed_at && (
                <span>· Completed {formatDate(selected.completed_at)}</span>
              )}
            </div>
            {selected.error_message && (
              <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/[.06] p-3 text-xs text-red-300">
                {selected.error_message}
              </div>
            )}
            <p className="label mt-5">Structured result</p>
            <pre className="max-h-[45vh] overflow-auto rounded-lg border border-line bg-void p-4 text-xs leading-5 text-slate-400">
              {selected.result != null
                ? JSON.stringify(selected.result, null, 2)
                : "No result is available yet."}
            </pre>
            {canIssueTasks(user?.role) &&
              (selected.status === "QUEUED" ||
                selected.status === "DISPATCHED") && (
                <div className="mt-5 flex justify-end">
                  <Button
                    variant="danger"
                    loading={cancelling}
                    onClick={() => void cancelTask()}
                  >
                    <Ban className="h-3.5 w-3.5" /> Cancel task
                  </Button>
                </div>
              )}
          </div>
        )}
      </Modal>
    </div>
  );
}
