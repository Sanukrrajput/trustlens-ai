import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react';
import { errorText } from '../lib/utils';

interface UseApiOptions<T> {
  enabled?: boolean;
  initialData?: T;
  onError?: (error: unknown) => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: DependencyList, options: UseApiOptions<T> = {}) {
  const { enabled = true, initialData, onError } = options;
  const [data, setData] = useState<T | undefined>(initialData);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      setData(result);
    } catch (err) {
      setError(errorText(err));
      onErrorRef.current?.(err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, refetch: load, setData };
}
