import { LockKeyhole, Play, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../context/useAuth";
import { useToast } from "../context/useToast";
import { canIssueTasks, humanize } from "../lib/utils";
import { api } from "../services/api";
import { TASK_TYPES, type KandorTask, type TaskType } from "../types";
import { Button, Select } from "./ui";

export function TaskForm({
  agentId,
  agentName,
  onCreated,
}: {
  agentId: string;
  agentName: string;
  onCreated?: (task: KandorTask) => void;
}) {
  const { user } = useAuth();
  const { notify } = useToast();
  const [taskType, setTaskType] = useState<TaskType>("SYSTEM_INFO");
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
      setError("Select an approved diagnostic task.");
      return;
    }
    setSubmitting(true);
    try {
      const task = await api.tasks.create(agentId, taskType);
      notify(`${humanize(taskType)} queued for ${agentName}.`);
      onCreated?.(task);
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
        Approved diagnostic
      </label>
      <Select
        id="task-type"
        aria-label="Approved diagnostic task"
        value={taskType}
        onChange={(event) => setTaskType(event.target.value as TaskType)}
      >
        {TASK_TYPES.map((type) => (
          <option key={type} value={type}>
            {humanize(type)}
          </option>
        ))}
      </Select>
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-kandor-400/15 bg-kandor-400/[.035] p-3">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-kandor-400" />
        <p className="text-[11px] leading-4 text-slate-500">
          This request contains an enum and an empty parameter object only.
          KANDOR never sends shell commands or executable text.
        </p>
      </div>
      {error && (
        <p
          className="mt-3 rounded-md border border-red-500/20 bg-red-500/[.06] p-2.5 text-xs text-red-300"
          role="alert"
        >
          {error}
        </p>
      )}
      <Button className="mt-4 w-full" type="submit" loading={submitting}>
        <Play className="h-3.5 w-3.5" /> Queue diagnostic
      </Button>
    </form>
  );
}
