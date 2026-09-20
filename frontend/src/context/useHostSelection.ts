import { createContext, useContext } from "react";
import type { Agent } from "../types";

export type SelectedHost = Pick<Agent, "id" | "name" | "hostname" | "status">;

export interface HostSelectionContextValue {
  selectedHosts: SelectedHost[];
  selectedIds: ReadonlySet<string>;
  isSelected: (id: string) => boolean;
  toggleHost: (host: SelectedHost) => void;
  selectHosts: (hosts: SelectedHost[]) => void;
  deselectHosts: (ids: string[]) => void;
  clearSelection: () => void;
}

const noop = () => undefined;

export const HostSelectionContext = createContext<HostSelectionContextValue>({
  selectedHosts: [],
  selectedIds: new Set(),
  isSelected: () => false,
  toggleHost: noop,
  selectHosts: noop,
  deselectHosts: noop,
  clearSelection: noop,
});

export function useHostSelection() {
  return useContext(HostSelectionContext);
}
