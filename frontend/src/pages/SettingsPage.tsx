import {
  Clock3,
  Copy,
  KeyRound,
  Plus,
  RotateCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  PageHeader,
  SectionTitle,
  Spinner,
} from "../components/ui";
import { useToast } from "../context/useToast";
import { useResource } from "../hooks/useResource";
import { formatDate, formatRelativeTime } from "../lib/utils";
import { api } from "../services/api";
import type { EnrollmentToken, AshborneSettings } from "../types";

const defaultSettings: AshborneSettings = {
  heartbeat_interval_seconds: 30,
  degraded_threshold_seconds: 60,
  offline_threshold_seconds: 300,
  task_expiration_seconds: 3600,
  session_timeout_minutes: 60,
  page_size: 50,
  audit_retention_days: 365,
};

interface SettingField {
  key: keyof AshborneSettings;
  label: string;
  description: string;
  suffix: string;
  min: number;
  max: number;
}

const fields: SettingField[] = [
  {
    key: "heartbeat_interval_seconds",
    label: "Heartbeat interval",
    description: "Expected interval between normal agent check-ins.",
    suffix: "seconds",
    min: 5,
    max: 3600,
  },
  {
    key: "degraded_threshold_seconds",
    label: "Degraded threshold",
    description: "Mark an agent degraded after this much silence.",
    suffix: "seconds",
    min: 10,
    max: 86400,
  },
  {
    key: "offline_threshold_seconds",
    label: "Offline threshold",
    description: "Mark an agent offline after this much silence.",
    suffix: "seconds",
    min: 20,
    max: 604800,
  },
  {
    key: "task_expiration_seconds",
    label: "Task expiration",
    description: "Expire queued lab actions that are not dispatched.",
    suffix: "seconds",
    min: 60,
    max: 604800,
  },
  {
    key: "session_timeout_minutes",
    label: "Session timeout",
    description: "Maximum authenticated session lifetime.",
    suffix: "minutes",
    min: 5,
    max: 1440,
  },
  {
    key: "page_size",
    label: "Default page size",
    description: "Default records shown in paginated views.",
    suffix: "rows",
    min: 1,
    max: 500,
  },
  {
    key: "audit_retention_days",
    label: "Audit retention",
    description: "Retention policy for immutable audit records.",
    suffix: "days",
    min: 30,
    max: 3650,
  },
];

export function SettingsPage() {
  const { notify } = useToast();
  const settingsResource = useResource(() => api.settings.get(), []);
  const tokenResource = useResource(() => api.enrollment.list(), []);
  const [settings, setSettings] = useState<AshborneSettings>(defaultSettings);
  const [saving, setSaving] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [tokenDialog, setTokenDialog] = useState(false);
  const [tokenDescription, setTokenDescription] = useState("");
  const [tokenLifetime, setTokenLifetime] = useState(900);
  const [creatingToken, setCreatingToken] = useState(false);
  const [createdToken, setCreatedToken] = useState<EnrollmentToken | null>(
    null,
  );

  useEffect(() => {
    if (settingsResource.data)
      setSettings({ ...defaultSettings, ...settingsResource.data });
  }, [settingsResource.data]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSettingsError("");
    if (
      settings.offline_threshold_seconds <= settings.degraded_threshold_seconds
    ) {
      setSettingsError(
        "The offline threshold must be greater than the degraded threshold.",
      );
      return;
    }
    setSaving(true);
    try {
      const updated = await api.settings.update(settings);
      setSettings(updated);
      notify("ASHBORNE configuration saved.");
    } catch (caught) {
      setSettingsError(
        caught instanceof Error
          ? caught.message
          : "Configuration could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  };

  const createToken = async (event: FormEvent) => {
    event.preventDefault();
    setCreatingToken(true);
    try {
      const token = await api.enrollment.create({
        expires_in_seconds: tokenLifetime,
        description: tokenDescription.trim() || undefined,
      });
      setCreatedToken(token);
      setTokenDialog(false);
      setTokenDescription("");
      notify("One-time enrollment token created.");
      void tokenResource.reload();
    } catch (caught) {
      notify(
        caught instanceof Error
          ? caught.message
          : "Enrollment token could not be created.",
        "error",
      );
    } finally {
      setCreatingToken(false);
    }
  };

  const revokeToken = async (token: EnrollmentToken) => {
    try {
      await api.enrollment.revoke(token.id);
      notify("Enrollment token revoked.");
      void tokenResource.reload();
    } catch (caught) {
      notify(
        caught instanceof Error
          ? caught.message
          : "Enrollment token could not be revoked.",
        "error",
      );
    }
  };

  const copyToken = async () => {
    if (!createdToken?.token) return;
    try {
      await navigator.clipboard.writeText(createdToken.token);
      notify("Token copied to clipboard.");
    } catch {
      notify("Clipboard access was denied. Copy the token manually.", "error");
    }
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="System control"
        title="Settings"
        description="Configure lab-host health, session, retention, and enrollment policy."
      />
      <div className="grid gap-4 xl:grid-cols-[1fr_430px]">
        <Card className="overflow-hidden">
          <SectionTitle
            title="Operational policy"
            description="Changes apply server-wide and generate an audit event."
            action={<SlidersHorizontal className="h-4 w-4 text-slate-600" />}
          />
          {settingsResource.loading ? (
            <Spinner label="Loading configuration" />
          ) : settingsResource.error && !settingsResource.data ? (
            <ErrorState
              error={settingsResource.error}
              onRetry={() => void settingsResource.reload()}
            />
          ) : (
            <form onSubmit={save}>
              <div className="grid gap-x-8 px-5 py-2 md:grid-cols-2">
                {fields.map((field) => (
                  <div key={field.key} className="border-b border-line/50 py-4">
                    <label
                      className="flex items-center justify-between gap-4 text-xs font-semibold text-slate-200"
                      htmlFor={`setting-${field.key}`}
                    >
                      <span>{field.label}</span>
                      <span className="relative w-32">
                        <Input
                          id={`setting-${field.key}`}
                          type="number"
                          min={field.min}
                          max={field.max}
                          required
                          value={settings[field.key]}
                          className="pr-14 text-right font-mono"
                          onChange={(event) =>
                            setSettings({
                              ...settings,
                              [field.key]: Number(event.target.value),
                            })
                          }
                        />
                        <span className="pointer-events-none absolute right-2 top-3 text-[9px] uppercase text-slate-600">
                          {field.suffix}
                        </span>
                      </span>
                    </label>
                    <p className="mt-1 max-w-sm pr-36 text-[11px] leading-4 text-slate-600">
                      {field.description}
                    </p>
                  </div>
                ))}
              </div>
              {settingsError && (
                <p
                  className="mx-5 mb-4 rounded-lg border border-red-500/20 bg-red-500/[.06] p-3 text-xs text-red-300"
                  role="alert"
                >
                  {settingsError}
                </p>
              )}
              <div className="flex justify-end gap-2 border-t border-line/70 px-5 py-4">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    setSettings(settingsResource.data ?? defaultSettings)
                  }
                >
                  <RotateCw className="h-3.5 w-3.5" /> Reset
                </Button>
                <Button type="submit" loading={saving}>
                  <Save className="h-3.5 w-3.5" /> Save configuration
                </Button>
              </div>
            </form>
          )}
        </Card>

        <div className="space-y-4">
          <Card className="overflow-hidden">
            <SectionTitle
              title="Enrollment tokens"
              description="Short-lived, single-use agent bootstrap secrets"
              action={
                <Button size="sm" onClick={() => setTokenDialog(true)}>
                  <Plus className="h-3.5 w-3.5" /> Generate
                </Button>
              }
            />
            {tokenResource.loading ? (
              <Spinner label="Loading tokens" />
            ) : tokenResource.error && !tokenResource.data ? (
              <ErrorState
                error={tokenResource.error}
                onRetry={() => void tokenResource.reload()}
              />
            ) : tokenResource.data?.items.length ? (
              <div className="max-h-[420px] divide-y divide-line/50 overflow-auto">
                {tokenResource.data.items.map((token) => {
                  const revoked = Boolean(token.revoked_at);
                  const used = Boolean(token.used_at);
                  const expired =
                    new Date(token.expires_at).getTime() <= Date.now();
                  return (
                    <div key={token.id} className="p-4">
                      <div className="flex items-start gap-3">
                        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-void">
                          <KeyRound className="h-3.5 w-3.5 text-slate-500" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium text-slate-300">
                            {token.description || "Agent enrollment"}
                          </p>
                          <p className="mt-1 text-[10px] text-slate-600">
                            Expires {formatRelativeTime(token.expires_at)}
                          </p>
                        </div>
                        <Badge
                          tone={
                            revoked || expired
                              ? "danger"
                              : used
                                ? "neutral"
                                : "success"
                          }
                        >
                          {revoked
                            ? "Revoked"
                            : expired
                              ? "Expired"
                              : used
                                ? "Used"
                                : "Active"}
                        </Badge>
                      </div>
                      {!revoked && !used && !expired && (
                        <div className="mt-3 flex justify-end">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-400"
                            onClick={() => void revokeToken(token)}
                          >
                            <Trash2 className="h-3 w-3" /> Revoke
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="No enrollment tokens"
                description="Generate a short-lived token when an agent is ready to enroll."
                icon={<KeyRound className="h-5 w-5" />}
              />
            )}
          </Card>

          <Card className="border-ashborne-400/15 bg-ashborne-400/[.025] p-5">
            <div className="flex gap-3">
              <ShieldCheck className="h-5 w-5 shrink-0 text-ashborne-400" />
              <div>
                <h3 className="text-sm font-semibold text-slate-200">
                  Secure-by-default policy
                </h3>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  Agents authenticate with independent credentials after
                  enrollment. Tokens expire, are single-use, revocable, and
                  never displayed again after creation.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>

      <Modal
        open={tokenDialog}
        title="Generate enrollment token"
        description="Use only on the intended agent. The secret will be shown once."
        onClose={() => setTokenDialog(false)}
      >
        <form className="space-y-4 p-5" onSubmit={createToken}>
          <div>
            <label className="label" htmlFor="token-description">
              Description
            </label>
            <Input
              id="token-description"
              maxLength={120}
              placeholder="Example: lab workstation 04"
              value={tokenDescription}
              onChange={(event) => setTokenDescription(event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="token-lifetime">
              Lifetime
            </label>
            <select
              id="token-lifetime"
              className="field"
              value={tokenLifetime}
              onChange={(event) => setTokenLifetime(Number(event.target.value))}
            >
              <option value={300}>5 minutes</option>
              <option value={900}>15 minutes</option>
              <option value={3600}>1 hour</option>
              <option value={86400}>24 hours</option>
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setTokenDialog(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={creatingToken}>
              <Clock3 className="h-3.5 w-3.5" /> Generate token
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(createdToken)}
        title="Enrollment token created"
        description={`Expires ${createdToken ? formatDate(createdToken.expires_at) : ""}`}
        onClose={() => setCreatedToken(null)}
      >
        {createdToken && (
          <div className="p-5">
            <p className="text-xs leading-5 text-amber-300">
              This secret is displayed once. Copy it now and close this dialog
              only after it is stored securely.
            </p>
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-ashborne-400/20 bg-void p-3">
              <code className="min-w-0 flex-1 break-all font-mono text-xs text-ashborne-200">
                {createdToken.token || "Token was not returned by the server."}
              </code>
              <Button
                size="sm"
                variant="secondary"
                disabled={!createdToken.token}
                onClick={() => void copyToken()}
              >
                <Copy className="h-3.5 w-3.5" /> Copy
              </Button>
            </div>
            <p className="mt-4 rounded-lg border border-line bg-void/40 p-3 font-mono text-[10px] leading-5 text-slate-500">
              ashborne-agent enroll --server https://ashborne.local --token
              &lt;TOKEN&gt;
            </p>
            <div className="mt-5 flex justify-end">
              <Button onClick={() => setCreatedToken(null)}>
                I have stored the token
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
