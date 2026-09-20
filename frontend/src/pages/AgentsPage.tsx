import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Play,
  Search,
  ShieldCheck,
  SquareTerminal,
  Tags,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BulkTaskDialog } from "../components/BulkTaskDialog";
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
  StatusBadge,
} from "../components/ui";
import { useLive } from "../context/useLive";
import { useAuth } from "../context/useAuth";
import { useHostSelection } from "../context/useHostSelection";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useResource } from "../hooks/useResource";
import { canIssueTasks, formatRelativeTime } from "../lib/utils";
import { api } from "../services/api";
import type { Agent } from "../types";

type SortKey =
  | "name"
  | "hostname"
  | "operating_system"
  | "agent_version"
  | "last_seen"
  | "status";

function SortButton({
  label,
  column,
  active,
  direction,
  onSort,
}: {
  label: string;
  column: SortKey;
  active: SortKey;
  direction: "asc" | "desc";
  onSort: (column: SortKey) => void;
}) {
  const Icon =
    active !== column ? ArrowUpDown : direction === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      className="group inline-flex items-center gap-1 hover:text-slate-300"
      aria-label={`Sort by ${label}${active === column ? ` (${direction}ending)` : ""}`}
      onClick={() => onSort(column)}
    >
      {label}
      <Icon className="h-3 w-3 text-slate-700 group-hover:text-slate-400" />
    </button>
  );
}

export function AgentsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const selection = useHostSelection();
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [tag, setTag] = useState("");
  const [skip, setSkip] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>("last_seen");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const { agentsRevision } = useLive();
  const debouncedSearch = useDebouncedValue(draftSearch.trim());

  useEffect(() => {
    setSearch(debouncedSearch);
    setSkip(0);
  }, [debouncedSearch]);

  const resource = useResource(
    () =>
      api.agents.list({
        search,
        status,
        tag,
        sort_by: sortKey,
        sort_order: sortDirection,
        skip,
      }),
    [search, status, tag, sortKey, sortDirection, skip, agentsRevision],
  );

  const agents = useMemo(() => resource.data?.items ?? [], [resource.data?.items]);
  const selectable = canIssueTasks(user?.role);
  const visibleIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const selectedVisible = useMemo(
    () => visibleIds.filter((id) => selection.selectedIds.has(id)).length,
    [selection.selectedIds, visibleIds],
  );
  const allVisibleSelected = Boolean(
    visibleIds.length && selectedVisible === visibleIds.length,
  );

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setSkip(0);
    setSearch(draftSearch.trim());
  };

  const sort = useCallback((column: SortKey) => {
    if (sortKey === column)
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
    else {
      setSortKey(column);
      setSortDirection("asc");
    }
  }, [sortKey]);

  const toggleVisible = useCallback(() => {
    if (allVisibleSelected) selection.deselectHosts(visibleIds);
    else selection.selectHosts(agents);
  }, [agents, allVisibleSelected, selection, visibleIds]);

  const clearFilters = () => {
    setDraftSearch("");
    setSearch("");
    setStatus("");
    setTag("");
    setSkip(0);
  };
  const filtersActive = Boolean(search || status || tag);

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Authorized target scope"
        title="Lab hosts"
        description="Search and inspect enrolled hosts that are explicitly in scope for this lab."
        actions={
          <div className="rounded-lg border border-line bg-panel px-3 py-2 text-xs text-slate-500">
            <span className="font-semibold text-slate-200">
              {resource.data?.total ?? 0}
            </span>{" "}
            enrolled
          </div>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line/70 p-4 lg:flex-row lg:items-center">
          <form className="relative flex-1 lg:max-w-md" onSubmit={submitSearch}>
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-600" />
            <Input
              aria-label="Search lab hosts"
              className="pl-9 pr-9"
              placeholder="Search name, hostname, UUID, or IP…"
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
            />
            {draftSearch && (
              <button
                type="button"
                aria-label="Clear agent search"
                className="absolute right-2 top-2 grid h-6 w-6 place-items-center text-slate-600 hover:text-slate-300"
                onClick={() => {
                  setDraftSearch("");
                  setSearch("");
                  setSkip(0);
                }}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </form>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <div className="relative">
              <Select
                aria-label="Agent status"
                className="min-w-36"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setSkip(0);
                }}
              >
                <option value="">All statuses</option>
                <option value="ONLINE">Online</option>
                <option value="DEGRADED">Degraded</option>
                <option value="OFFLINE">Offline</option>
              </Select>
            </div>
            <div className="relative">
              <Tags className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-600" />
              <Input
                aria-label="Filter by tag"
                className="pl-9 sm:w-40"
                placeholder="Filter tag"
                value={tag}
                onChange={(event) => {
                  setTag(event.target.value);
                  setSkip(0);
                }}
              />
            </div>
            {filtersActive && (
              <Button type="button" variant="ghost" onClick={clearFilters}>
                Clear
              </Button>
            )}
          </div>
        </div>

        {resource.loading ? (
          <Spinner label="Locating lab hosts" />
        ) : resource.error && !resource.data ? (
          <ErrorState
            error={resource.error}
            onRetry={() => void resource.reload()}
          />
        ) : agents.length ? (
          <>
            <div className="overflow-x-auto">
              <table
                className="w-full border-collapse"
                aria-label="ASHBORNE lab hosts"
              >
                <thead className="border-b border-line/70 bg-void/25">
                  <tr>
                    {selectable && (
                      <th className="w-12 px-4 py-3">
                        <input
                          aria-label="Select all visible lab hosts"
                          className="h-4 w-4 accent-ashborne-400"
                          type="checkbox"
                          checked={allVisibleSelected}
                          onChange={toggleVisible}
                        />
                      </th>
                    )}
                    <th className="table-heading">
                      <SortButton
                        label="Enrollment"
                        column="name"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                    <th className="table-heading">
                      <SortButton
                        label="Host"
                        column="hostname"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                    <th className="table-heading">
                      <SortButton
                        label="Platform"
                        column="operating_system"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                    <th className="table-heading">
                      <SortButton
                        label="Version"
                        column="agent_version"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                    <th className="table-heading">Network</th>
                    <th className="table-heading">Tags</th>
                    <th className="table-heading">
                      <SortButton
                        label="Last seen"
                        column="last_seen"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                    <th className="table-heading">
                      <SortButton
                        label="Status"
                        column="status"
                        active={sortKey}
                        direction={sortDirection}
                        onSort={sort}
                      />
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/50">
                  {agents.map((agent: Agent) => (
                    <tr
                      key={agent.id}
                      className={`group transition hover:bg-white/[.025] ${selection.isSelected(agent.id) ? "bg-ashborne-400/[.045]" : ""}`}
                    >
                      {selectable && (
                        <td className="w-12 px-4 py-3.5">
                          <input
                            aria-label={`Select ${agent.name || agent.hostname}`}
                            className="h-4 w-4 accent-ashborne-400"
                            type="checkbox"
                            checked={selection.isSelected(agent.id)}
                            onChange={() => selection.toggleHost(agent)}
                          />
                        </td>
                      )}
                      <td className="table-cell">
                        <Link
                          to={`/agents/${agent.id}`}
                          className="flex items-center gap-3"
                        >
                          <span className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-void text-slate-500 transition group-hover:border-ashborne-400/25 group-hover:text-ashborne-400">
                            <ShieldCheck className="h-4 w-4" />
                          </span>
                          <span>
                            <span className="block font-medium text-slate-100 group-hover:text-ashborne-200">
                              {agent.name || agent.hostname}
                            </span>
                            <span className="mt-0.5 block max-w-40 truncate font-mono text-[10px] text-slate-700">
                              {agent.uuid || agent.id}
                            </span>
                          </span>
                        </Link>
                      </td>
                      <td className="table-cell">
                        <span className="block text-slate-300">
                          {agent.hostname}
                        </span>
                        <span className="mt-0.5 block text-[10px] text-slate-600">
                          {agent.username || "Unknown user"}
                        </span>
                      </td>
                      <td className="table-cell">
                        <span className="block">{agent.operating_system}</span>
                        <span className="mt-0.5 block text-[10px] text-slate-600">
                          {agent.os_version || "—"} ·{" "}
                          {agent.architecture || "—"}
                        </span>
                      </td>
                      <td className="table-cell font-mono text-xs">
                        {agent.agent_version}
                      </td>
                      <td className="table-cell font-mono text-xs text-slate-500">
                        {agent.ip_address || "—"}
                      </td>
                      <td className="table-cell">
                        <div className="flex max-w-56 flex-wrap gap-1">
                          {agent.tags.map((item) => (
                            <Badge key={item}>{item}</Badge>
                          ))}
                          {!agent.tags.length && (
                            <span className="text-slate-700">—</span>
                          )}
                        </div>
                      </td>
                      <td className="table-cell">
                        <span
                          title={
                            agent.last_seen
                              ? new Date(agent.last_seen).toLocaleString()
                              : "Never"
                          }
                        >
                          {formatRelativeTime(agent.last_seen)}
                        </span>
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={agent.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              skip={resource.data?.skip ?? skip}
              limit={resource.data?.limit ?? 25}
              total={resource.data?.total ?? 0}
              onChange={setSkip}
            />
          </>
        ) : (
          <EmptyState
            title="No lab hosts match"
            description={
              filtersActive
                ? "Adjust or clear the active search filters."
                : "Enroll an ASHBORNE agent on an authorized lab host to begin adversary-emulation training."
            }
            icon={<ShieldCheck className="h-5 w-5" />}
          />
        )}
      </Card>

      {selectable && selection.selectedHosts.length > 0 && (
        <div className="sticky bottom-4 z-20 mt-4 flex flex-col gap-3 rounded-xl border border-ashborne-400/25 bg-[#151315]/95 px-4 py-3 shadow-2xl backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[.14em] text-slate-100">
              {selection.selectedHosts.length} host{selection.selectedHosts.length === 1 ? "" : "s"} selected
            </p>
            <p className="mt-0.5 text-[10px] text-slate-600">
              Selection persists while using task controls and the console.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setBulkDialogOpen(true)}>
              <Play className="h-3.5 w-3.5" /> Run task
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate("/console")}
            >
              <SquareTerminal className="h-3.5 w-3.5" /> Open console
            </Button>
            <Button
              aria-label="Deselect all hosts"
              size="sm"
              variant="ghost"
              onClick={selection.clearSelection}
            >
              Clear
            </Button>
          </div>
        </div>
      )}

      <BulkTaskDialog
        open={bulkDialogOpen}
        hosts={selection.selectedHosts}
        onClose={() => setBulkDialogOpen(false)}
      />
    </div>
  );
}
