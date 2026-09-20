import { ArrowLeft, Play, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { SelectedHost } from "../context/useHostSelection";
import { useToast } from "../context/useToast";
import { humanize } from "../lib/utils";
import { api } from "../services/api";
import {
  TASK_CATEGORIES,
  TASK_DESCRIPTIONS,
  type TaskType,
} from "../types";
import { Button, Modal, Select, StatusBadge } from "./ui";

export function BulkTaskDialog({
  open,
  hosts,
  onClose,
}: {
  open: boolean;
  hosts: SelectedHost[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const { notify } = useToast();
  const [taskType, setTaskType] = useState<TaskType>("QUICK_RECON");
  const [reviewing, setReviewing] = useState(false);
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) return;
    setReviewing(false);
    setScopeConfirmed(false);
    setError("");
  }, [open]);

  const dispatch = async () => {
    if (!scopeConfirmed || !hosts.length) return;
    setSubmitting(true);
    setError("");
    try {
      const operation = await api.tasks.bulkCreate(
        hosts.map((host) => host.id),
        taskType,
        true,
      );
      notify(
        `${humanize(taskType)} queued as ${hosts.length} independent tasks.`,
      );
      onClose();
      navigate(`/bulk-operations/${operation.bulk_operation_id}`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The bulk operation could not be queued.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={reviewing ? "Review bulk operation" : "Run task on selected hosts"}
      description={`${hosts.length} authorized lab host${hosts.length === 1 ? "" : "s"} selected`}
      onClose={onClose}
      width="max-w-2xl"
    >
      <div className="p-5">
        {!reviewing ? (
          <>
            <label className="label" htmlFor="bulk-task-type">
              Approved lab action
            </label>
            <Select
              id="bulk-task-type"
              value={taskType}
              onChange={(event) => setTaskType(event.target.value as TaskType)}
            >
              {Object.entries(TASK_CATEGORIES).map(([category, taskTypes]) => (
                <optgroup key={category} label={category}>
                  {taskTypes.map((type) => (
                    <option key={type} value={type}>
                      {humanize(type)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              {TASK_DESCRIPTIONS[taskType]}
            </p>
            <div className="mt-4 rounded-lg bg-void/55 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-[.14em] text-slate-500">
                Parameters
              </p>
              <p className="mt-1 text-xs text-slate-400">
                This bounded action uses its validated default parameters.
              </p>
            </div>
            <div className="mt-5 flex justify-end">
              <Button disabled={!hosts.length} onClick={() => setReviewing(true)}>
                Review {hosts.length} targets
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4 rounded-lg bg-void/55 p-3">
              <div>
                <p className="font-mono text-sm font-semibold text-slate-100">
                  {taskType}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  One independently audited task will be created per host.
                </p>
              </div>
              <span className="font-mono text-xs text-ashborne-300">
                {hosts.length} TASKS
              </span>
            </div>
            <div className="mt-4 max-h-60 divide-y divide-line/50 overflow-auto rounded-lg border border-line/70">
              {hosts.map((host) => (
                <div
                  key={host.id}
                  className="flex items-center justify-between gap-3 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200">
                      {host.name || host.hostname}
                    </p>
                    <p className="truncate font-mono text-[10px] text-slate-600">
                      {host.hostname} · {host.id}
                    </p>
                  </div>
                  <StatusBadge status={host.status} />
                </div>
              ))}
            </div>
            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-lg border border-ashborne-400/20 bg-ashborne-400/[.04] p-3 text-xs leading-5 text-slate-300">
              <input
                aria-label="Confirm authorized scope for selected hosts"
                className="mt-0.5 h-4 w-4 accent-ashborne-400"
                type="checkbox"
                checked={scopeConfirmed}
                onChange={(event) => setScopeConfirmed(event.target.checked)}
              />
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ashborne-400" />
              <span>
                I confirm every selected host is owned by me or explicitly
                included in the authorized lab scope.
              </span>
            </label>
            {error && (
              <p className="mt-3 rounded-lg border border-red-500/20 bg-red-500/[.06] p-3 text-xs text-red-300" role="alert">
                {error}
              </p>
            )}
            <div className="mt-5 flex justify-between gap-3">
              <Button variant="ghost" onClick={() => setReviewing(false)}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              <Button
                loading={submitting}
                disabled={!scopeConfirmed}
                onClick={() => void dispatch()}
              >
                <Play className="h-4 w-4" /> Run {hosts.length} tasks
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
