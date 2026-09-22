import { useCallback, useMemo, useState, type ReactNode } from "react";
import { HostSelectionContext, type SelectedHost } from "./useHostSelection";

const STORAGE_KEY = "ashborne.selected-hosts";
const HOST_STATUSES = new Set(["ONLINE", "DEGRADED", "OFFLINE"]);

function compactHost(host: SelectedHost): SelectedHost {
  return {
    id: host.id,
    name: host.name,
    hostname: host.hostname,
    status: host.status,
  };
}

function sameHost(left: SelectedHost, right: SelectedHost) {
  return (
    left.id === right.id &&
    left.name === right.name &&
    left.hostname === right.hostname &&
    left.status === right.status
  );
}

function restoreSelection(): SelectedHost[] {
  try {
    const value = sessionStorage.getItem(STORAGE_KEY);
    const parsed: unknown = value ? JSON.parse(value) : [];
    if (!Array.isArray(parsed)) return [];
    const restored = parsed
      .filter((host): host is SelectedHost =>
        Boolean(
          host &&
          typeof host === "object" &&
          typeof (host as SelectedHost).id === "string" &&
          typeof (host as SelectedHost).name === "string" &&
          typeof (host as SelectedHost).hostname === "string" &&
          HOST_STATUSES.has((host as SelectedHost).status),
        ),
      )
      .map(compactHost);
    return [...new Map(restored.map((host) => [host.id, host])).values()];
  } catch {
    return [];
  }
}

export function HostSelectionProvider({ children }: { children: ReactNode }) {
  const [selectedHosts, setSelectedHosts] =
    useState<SelectedHost[]>(restoreSelection);

  const update = useCallback(
    (updater: (current: SelectedHost[]) => SelectedHost[]) => {
      setSelectedHosts((current) => {
        const next = updater(current);
        if (next !== current)
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
    },
    [],
  );

  const toggleHost = useCallback(
    (host: SelectedHost) => {
      const selectedHost = compactHost(host);
      update((current) =>
        current.some((item) => item.id === host.id)
          ? current.filter((item) => item.id !== host.id)
          : [...current, selectedHost],
      );
    },
    [update],
  );

  const selectHosts = useCallback(
    (hosts: SelectedHost[]) =>
      update((current) => {
        const selected = new Map(current.map((host) => [host.id, host]));
        let changed = false;
        hosts.forEach((source) => {
          const host = compactHost(source);
          const existing = selected.get(host.id);
          if (!existing || !sameHost(existing, host)) {
            selected.set(host.id, host);
            changed = true;
          }
        });
        return changed ? [...selected.values()] : current;
      }),
    [update],
  );

  const deselectHosts = useCallback(
    (ids: string[]) => {
      const removing = new Set(ids);
      update((current) => current.filter((host) => !removing.has(host.id)));
    },
    [update],
  );

  const clearSelection = useCallback(() => update(() => []), [update]);
  const selectedIds = useMemo(
    () => new Set(selectedHosts.map((host) => host.id)),
    [selectedHosts],
  );
  const isSelected = useCallback(
    (id: string) => selectedIds.has(id),
    [selectedIds],
  );
  const value = useMemo(
    () => ({
      selectedHosts,
      selectedIds,
      isSelected,
      toggleHost,
      selectHosts,
      deselectHosts,
      clearSelection,
    }),
    [
      selectedHosts,
      selectedIds,
      isSelected,
      toggleHost,
      selectHosts,
      deselectHosts,
      clearSelection,
    ],
  );

  return (
    <HostSelectionContext.Provider value={value}>
      {children}
    </HostSelectionContext.Provider>
  );
}
