import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DependencyList,
} from "react";

export interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: Error | null;
  reload: () => Promise<void>;
}

export function useResource<T>(
  loader: () => Promise<T>,
  dependencies: DependencyList,
): ResourceState<T> {
  const mounted = useRef(true);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // The caller controls invalidation explicitly with the dependency list.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(async () => {
    if (data === null) setLoading(true);
    else setRefreshing(true);
    try {
      const result = await loader();
      if (!mounted.current) return;
      setData(result);
      setError(null);
    } catch (caught) {
      if (!mounted.current) return;
      setError(
        caught instanceof Error ? caught : new Error("Something went wrong"),
      );
    } finally {
      if (mounted.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, loading, refreshing, error, reload };
}
