import { LockKeyhole, Play, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../context/useAuth";
import { useToast } from "../context/useToast";
import { canIssueTasks, humanize } from "../lib/utils";
import { api } from "../services/api";
import {
  TASK_CATEGORIES,
  TASK_DESCRIPTIONS,
  TASK_TYPES,
  type AshborneTask,
  type TaskType,
} from "../types";
import { Button, Select } from "./ui";

export function TaskForm({
  agentId,
  agentName,
  onCreated,
}: {
  agentId: string;
  agentName: string;
  onCreated?: (task: AshborneTask) => void;
}) {
  const { user } = useAuth();
  const { notify } = useToast();
  const [taskType, setTaskType] = useState<TaskType>("QUICK_RECON");
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!canIssueTasks(user?.role)) {
    return (
      <div className="rounded-lg border border-line bg-void/40 p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-400">
          <LockKeyhole className="h-4 w-4" /> Read-only role
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-600">
          Viewers can inspect task history and results but cannot issue work to
          agents.
        </p>
      </div>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!TASK_TYPES.includes(taskType)) {
      setError("Select an approved lab action.");
      return;
    }
    if (!scopeConfirmed) {
      setError("Confirm that this host is within your authorized lab scope.");
      return;
    }
    setSubmitting(true);
    try {
      const task = await api.tasks.create(agentId, taskType, scopeConfirmed);
      notify(`${humanize(taskType)} queued for ${agentName}.`);
      onCreated?.(task);
      setScopeConfirmed(false);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Task could not be queued.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <label className="label" htmlFor="task-type">
        Approved lab action
      </label>
      <Select
        id="task-type"
        aria-label="Approved lab action"
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
      <p className="mt-2 text-[11px] leading-4 text-slate-500">
        {TASK_DESCRIPTIONS[taskType]}
      </p>
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-ashborne-400/15 bg-ashborne-400/[.035] p-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ashborne-400" />
        <p className="text-[11px] leading-4 text-slate-500">
          This request uses a closed task type and validated parameters.
          ASHBORNE does not provide payload delivery, persistence, stealth
          controls, or an arbitrary shell.
        </p>
      </div>
      <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-lg border border-line bg-void/40 p-3 text-[11px] leading-4 text-slate-400">
        <input
          className="mt-0.5 h-4 w-4 accent-ashborne-400"
          type="checkbox"
          checked={scopeConfirmed}
          onChange={(event) => setScopeConfirmed(event.target.checked)}
        />
        <span>
          I confirm this enrolled host is owned by me or explicitly included in
          the authorized lab scope.
        </span>
      </label>
      {error && (
        <p
          className="mt-3 rounded-md border border-red-500/20 bg-red-500/[.06] p-2.5 text-xs text-red-300"
          role="alert"
        >
          {error}
        </p>
      )}
      <Button
        className="mt-4 w-full"
        type="submit"
        loading={submitting}
        disabled={!scopeConfirmed}
      >
        <Play className="h-3.5 w-3.5" /> Queue lab action
      </Button>
    </form>
  );
}
