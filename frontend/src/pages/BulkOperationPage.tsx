import {
  ArrowLeft,
  Ban,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Download,
  RefreshCw,
  RotateCw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { StructuredResult } from "../components/StructuredResult";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui";
import { useAuth } from "../context/useAuth";
import { useTasksRevision } from "../context/useLive";
import { useToast } from "../context/useToast";
import { useResource } from "../hooks/useResource";
import { canIssueTasks, formatDate, humanize } from "../lib/utils";
import { api } from "../services/api";
import type { AshborneTask } from "../types";

function saveJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function BulkOperationPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { notify } = useToast();
  const tasksRevision = useTasksRevision();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [failedOnly, setFailedOnly] = useState(false);
  const [action, setAction] = useState<"retry" | "cancel" | "rerun" | null>(
    null,
  );
  const resource = useResource(
    () => api.tasks.bulkOperation(id),
    [id, tasksRevision],
  );
  const operation = resource.data;

  useEffect(() => {
    if (!operation) return;
    setExpanded((current) => {
      if (current.size) return current;
      return new Set(
        operation.tasks
          .filter((task) => task.status === "FAILED")
          .map((task) => task.id),
      );
    });
  }, [operation]);

  const visibleTasks = useMemo(
    () =>
      operation?.tasks.filter(
        (task) => !failedOnly || task.status === "FAILED",
      ) ?? [],
    [failedOnly, operation],
  );

  const perform = async (kind: "retry" | "cancel" | "rerun") => {
    if (!operation) return;
    setAction(kind);
    try {
      if (kind === "cancel") {
        await api.tasks.cancelBulkQueued(operation.bulk_operation_id);
        notify("Queued tasks cancelled where supported.");
        void resource.reload();
      } else {
        const next =
          kind === "retry"
            ? await api.tasks.retryBulkFailed(operation.bulk_operation_id, true)
            : await api.tasks.rerunBulk(operation.bulk_operation_id, true);
        notify(
          kind === "retry"
            ? "Failed hosts requeued."
            : "Operation rerun queued.",
        );
        navigate(`/bulk-operations/${next.bulk_operation_id}`);
      }
    } catch (caught) {
      notify(
        caught instanceof Error ? caught.message : "The operation failed.",
        "error",
      );
    } finally {
      setAction(null);
    }
  };

  if (resource.loading) return <Spinner label="Loading bulk operation" />;
  if (resource.error || !operation)
    return (
      <ErrorState
        error={resource.error ?? "Bulk operation not found"}
        onRetry={() => void resource.reload()}
      />
    );

  const hasFailed =
    operation.status_counts.FAILED + operation.status_counts.TIMED_OUT > 0;
  const hasQueued =
    operation.status_counts.QUEUED + operation.status_counts.DISPATCHED > 0;
  const canOperate = canIssueTasks(user?.role);

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Bulk operation"
        title={humanize(operation.task_type)}
        description={`${operation.target_count} independent, audited host tasks · ${formatDate(operation.created_at)}`}
        actions={
          <Link to="/agents">
            <Button variant="secondary" size="sm">
              <ArrowLeft className="h-3.5 w-3.5" /> Return to hosts
            </Button>
          </Link>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["Targets", operation.target_count, "text-slate-100"],
            ["Complete", operation.status_counts.SUCCESS, "text-emerald-300"],
            ["Running", operation.status_counts.RUNNING, "text-slate-200"],
            [
              "Failed",
              operation.status_counts.FAILED +
                operation.status_counts.TIMED_OUT,
              "text-red-300",
            ],
            [
              "Queued",
              operation.status_counts.QUEUED +
                operation.status_counts.DISPATCHED,
              "text-slate-300",
            ],
          ].map(([label, value, tone]) => (
            <div
              key={String(label)}
              className="rounded-lg bg-void/50 px-4 py-3"
            >
              <p className="text-[9px] font-semibold uppercase tracking-[.14em] text-slate-600">
                {label}
              </p>
              <p className={`mt-1 font-mono text-xl font-semibold ${tone}`}>
                {value}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-3 break-all font-mono text-[10px] text-slate-700">
          {operation.bulk_operation_id}
        </p>
      </Card>

      <div className="mb-4 flex flex-col gap-3 rounded-xl border border-line/60 bg-panel/60 p-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              setExpanded(new Set(visibleTasks.map((task) => task.id)))
            }
          >
            Expand all
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded(new Set())}
          >
            Collapse all
          </Button>
          <Button
            size="sm"
            variant={failedOnly ? "danger" : "ghost"}
            onClick={() => setFailedOnly((current) => !current)}
          >
            Failed only
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              saveJson(
                `ashborne-${operation.bulk_operation_id}.json`,
                operation,
              )
            }
          >
            <Download className="h-3.5 w-3.5" /> Export JSON
          </Button>
        </div>
        {canOperate && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {hasFailed && (
              <Button
                size="sm"
                variant="secondary"
                loading={action === "retry"}
                onClick={() => void perform("retry")}
              >
                <RefreshCw className="h-3.5 w-3.5" /> Retry failed
              </Button>
            )}
            {hasQueued && (
              <Button
                size="sm"
                variant="danger"
                loading={action === "cancel"}
                onClick={() => void perform("cancel")}
              >
                <Ban className="h-3.5 w-3.5" /> Cancel queued
              </Button>
            )}
            <Button
              size="sm"
              loading={action === "rerun"}
              onClick={() => void perform("rerun")}
            >
              <RotateCw className="h-3.5 w-3.5" /> Rerun
            </Button>
          </div>
        )}
      </div>

      <div className="space-y-2">
        {visibleTasks.map((task: AshborneTask) => {
          const open = expanded.has(task.id);
          return (
            <Card key={task.id} className="overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  aria-label={`${open ? "Collapse" : "Expand"} ${task.agent_name || task.agent_id}`}
                  className="grid h-7 w-7 place-items-center rounded-md text-slate-600 hover:bg-white/5 hover:text-slate-300"
                  onClick={() =>
                    setExpanded((current) => {
                      const next = new Set(current);
                      if (next.has(task.id)) next.delete(task.id);
                      else next.add(task.id);
                      return next;
                    })
                  }
                >
                  {open ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-200">
                    {task.agent_name || task.agent_id}
                  </p>
                  <p className="truncate font-mono text-[10px] text-slate-700">
                    {task.id}
                  </p>
                </div>
                <StatusBadge status={task.status} />
                {task.result != null && (
                  <Button
                    aria-label={`Copy result for ${task.agent_name || task.agent_id}`}
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      void navigator.clipboard.writeText(
                        JSON.stringify(task.result, null, 2),
                      );
                      notify("Result copied.");
                    }}
                  >
                    <Clipboard className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
              {task.error_message && (
                <p className="mx-4 mb-3 rounded-md bg-red-500/[.07] p-2 text-xs text-red-300">
                  {task.error_message}
                </p>
              )}
              {open && (
                <div className="border-t border-line/50 p-4">
                  <StructuredResult task={task} />
                </div>
              )}
            </Card>
          );
        })}
        {!visibleTasks.length && (
          <Card>
            <EmptyState
              title={failedOnly ? "No failed hosts" : "No host tasks"}
              description={
                failedOnly
                  ? "This operation currently has no failed tasks."
                  : "Host tasks have not been attached to this operation."
              }
            />
          </Card>
        )}
      </div>
    </div>
  );
}
