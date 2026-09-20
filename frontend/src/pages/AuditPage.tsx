import {
  ChevronDown,
  ChevronRight,
  Filter,
  Fingerprint,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Pagination,
  Select,
  Spinner,
} from "../components/ui";
import { useLive } from "../context/useLive";
import { useResource } from "../hooks/useResource";
import { formatDate, humanize } from "../lib/utils";
import { api } from "../services/api";
import { AUDIT_EVENT_TYPES, type AuditEvent } from "../types";

function eventTone(
  eventType: string,
): "success" | "warning" | "danger" | "info" | "purple" | "neutral" {
  if (
    eventType.endsWith("FAILURE") ||
    eventType.endsWith("FAILED") ||
    eventType.endsWith("REMOVED")
  )
    return "danger";
  if (
    eventType.includes("LOGIN_SUCCESS") ||
    eventType.endsWith("COMPLETED") ||
    eventType.endsWith("ENROLLED")
  )
    return "success";
  if (eventType.includes("ROLE") || eventType.includes("TOKEN"))
    return "purple";
  if (
    eventType.includes("HEARTBEAT") ||
    eventType.includes("DISPATCHED") ||
    eventType.includes("STARTED")
  )
    return "info";
  if (eventType.endsWith("CREATED")) return "warning";
  return "neutral";
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [expanded, setExpanded] = useState(false);
  const hasMetadata = event.metadata && Object.keys(event.metadata).length > 0;
  return (
    <>
      <tr className="transition hover:bg-white/[.02]">
        <td className="table-cell w-8 pr-0">
          <button
            aria-label={`${expanded ? "Collapse" : "Expand"} audit event`}
            disabled={!hasMetadata}
            className="text-slate-600 hover:text-slate-300 disabled:opacity-20"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        </td>
        <td className="table-cell">
          <Badge tone={eventTone(event.event_type)}>{event.event_type}</Badge>
          <p className="mt-1 max-w-36 truncate font-mono text-[9px] text-slate-700">
            {event.id}
          </p>
        </td>
        <td className="table-cell">{formatDate(event.timestamp)}</td>
        <td className="table-cell">
          <p>{event.user_email || event.user_id || "System"}</p>
        </td>
        <td className="table-cell">
          {event.agent_name || event.agent_id || "—"}
        </td>
        <td className="table-cell font-mono text-xs text-slate-500">
          {event.source_ip || "—"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="bg-void/35 px-12 py-3">
            <p className="label">Event metadata</p>
            <pre className="max-h-52 overflow-auto rounded-md border border-line bg-void p-3 text-[11px] leading-5 text-slate-500">
              {JSON.stringify(event.metadata, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

export function AuditPage() {
  const { auditRevision } = useLive();
  const eventTypesResource = useResource(() => api.audit.eventTypes(), []);
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("");
  const [user, setUser] = useState("");
  const [agent, setAgent] = useState("");
  const [sourceIp, setSourceIp] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [skip, setSkip] = useState(0);
  const eventTypes = Array.from(
    new Set([...AUDIT_EVENT_TYPES, ...(eventTypesResource.data ?? [])]),
  ).sort();

  const startTime = startDate
    ? new Date(`${startDate}T00:00:00`).toISOString()
    : undefined;
  const endTime = endDate
    ? new Date(`${endDate}T23:59:59`).toISOString()
    : undefined;
  const resource = useResource(
    () =>
      api.audit.list({
        search,
        event_type: eventType,
        user,
        agent,
        source_ip: sourceIp,
        start_time: startTime,
        end_time: endTime,
        skip,
      }),
    [
      search,
      eventType,
      user,
      agent,
      sourceIp,
      startTime,
      endTime,
      skip,
      auditRevision,
    ],
  );

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setSearch(draftSearch.trim());
    setSkip(0);
  };
  const activeFilters = [
    search,
    eventType,
    user,
    agent,
    sourceIp,
    startDate,
    endDate,
  ].filter(Boolean).length;
  const clearFilters = () => {
    setDraftSearch("");
    setSearch("");
    setEventType("");
    setUser("");
    setAgent("");
    setSourceIp("");
    setStartDate("");
    setEndDate("");
    setSkip(0);
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Immutable record"
        title="Timeline / audit"
        description="Search the immutable operation timeline for authentication, enrollment, host, task, and administrative events."
        actions={
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/15 bg-emerald-500/[.04] px-3 py-2 text-[10px] font-semibold uppercase tracking-[.12em] text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" /> Append only
          </div>
        }
      />

      <Card className="mb-4 overflow-hidden">
        <div className="flex flex-col gap-3 p-4 lg:flex-row">
          <form className="relative flex-1" onSubmit={submitSearch}>
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-600" />
            <Input
              aria-label="Search audit log"
              className="pl-9"
              placeholder="Search event UUID, type, request ID, IP, or metadata…"
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
            />
          </form>
          <Select
            aria-label="Audit event type"
            className="lg:w-60"
            value={eventType}
            onChange={(event) => {
              setEventType(event.target.value);
              setSkip(0);
            }}
          >
            <option value="">All event types</option>
            {eventTypes.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </Select>
          <Button
            variant="secondary"
            onClick={() => setShowFilters((value) => !value)}
          >
            <Filter className="h-3.5 w-3.5" /> Filters
            {activeFilters > 0 && (
              <span className="grid h-5 min-w-5 place-items-center rounded bg-ashborne-400/15 px-1 text-[10px] text-ashborne-300">
                {activeFilters}
              </span>
            )}
          </Button>
        </div>
        {showFilters && (
          <div className="grid gap-3 border-t border-line/70 bg-void/20 p-4 md:grid-cols-2 xl:grid-cols-5">
            <div>
              <label className="label" htmlFor="audit-user">
                User
              </label>
              <Input
                id="audit-user"
                placeholder="Email or UUID"
                value={user}
                onChange={(event) => {
                  setUser(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            <div>
              <label className="label" htmlFor="audit-agent">
                Agent
              </label>
              <Input
                id="audit-agent"
                placeholder="Name or UUID"
                value={agent}
                onChange={(event) => {
                  setAgent(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            <div>
              <label className="label" htmlFor="audit-ip">
                Source IP
              </label>
              <Input
                id="audit-ip"
                placeholder="192.0.2.10"
                value={sourceIp}
                onChange={(event) => {
                  setSourceIp(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            <div>
              <label className="label" htmlFor="audit-start">
                From
              </label>
              <Input
                id="audit-start"
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            <div>
              <label className="label" htmlFor="audit-end">
                Through
              </label>
              <Input
                id="audit-end"
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            {activeFilters > 0 && (
              <div className="md:col-span-2 xl:col-span-5">
                <Button size="sm" variant="ghost" onClick={clearFilters}>
                  Clear all filters
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        {resource.loading ? (
          <Spinner label="Reading audit ledger" />
        ) : resource.error && !resource.data ? (
          <ErrorState
            error={resource.error}
            onRetry={() => void resource.reload()}
          />
        ) : resource.data?.items.length ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full" aria-label="ASHBORNE audit events">
                <thead className="border-b border-line/70 bg-void/25">
                  <tr>
                    <th className="table-heading w-8">
                      <span className="sr-only">Expand</span>
                    </th>
                    <th className="table-heading">Event</th>
                    <th className="table-heading">Timestamp</th>
                    <th className="table-heading">User</th>
                    <th className="table-heading">Agent</th>
                    <th className="table-heading">Source IP</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/50">
                  {resource.data.items.map((event) => (
                    <AuditRow key={event.id} event={event} />
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
            title="No audit events match"
            description={
              activeFilters
                ? "Adjust or clear filters to widen the immutable event search."
                : "Audit events will appear as users and agents interact with ASHBORNE."
            }
            icon={<Fingerprint className="h-5 w-5" />}
          />
        )}
      </Card>
    </div>
  );
}
