import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  HostSelectionContext,
  type SelectedHost,
} from "./useHostSelection";

const STORAGE_KEY = "ashborne.selected-hosts";

function restoreSelection(): SelectedHost[] {
  try {
    const value = sessionStorage.getItem(STORAGE_KEY);
    const parsed: unknown = value ? JSON.parse(value) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (host): host is SelectedHost =>
        Boolean(
          host &&
            typeof host === "object" &&
            typeof (host as SelectedHost).id === "string" &&
            typeof (host as SelectedHost).hostname === "string",
        ),
    );
  } catch {
    return [];
  }
}

export function HostSelectionProvider({ children }: { children: ReactNode }) {
  const [selectedHosts, setSelectedHosts] =
    useState<SelectedHost[]>(restoreSelection);

  const update = useCallback((updater: (current: SelectedHost[]) => SelectedHost[]) => {
    setSelectedHosts((current) => {
      const next = updater(current);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const toggleHost = useCallback(
    (host: SelectedHost) =>
      update((current) =>
        current.some((item) => item.id === host.id)
          ? current.filter((item) => item.id !== host.id)
          : [...current, host],
      ),
    [update],
  );

  const selectHosts = useCallback(
    (hosts: SelectedHost[]) =>
      update((current) => {
        const selected = new Map(current.map((host) => [host.id, host]));
        hosts.forEach((host) => selected.set(host.id, host));
        return [...selected.values()];
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
