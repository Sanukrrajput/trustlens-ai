import { useCallback, useEffect, useState } from 'react';
import { api } from './api';

export function useApi(path, params = {}, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [nonce, setNonce] = useState(0);
  const refetch = useCallback(() => setNonce((value) => value + 1), []);
  const serialized = JSON.stringify(params);

  useEffect(() => {
    let active = true;
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return undefined;
    }
    setState((previous) => ({ ...previous, loading: true, error: null }));
    api(path, { params: JSON.parse(serialized) })
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (active) setState({ data: null, loading: false, error: error.message });
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, serialized, nonce, ...deps]);

  return { ...state, refetch };
}

export function useAsyncAction() {
  const [state, setState] = useState({ loading: false, error: null, data: null });
  const run = useCallback(async (callback) => {
    setState({ loading: true, error: null, data: null });
    try {
      const data = await callback();
      setState({ loading: false, error: null, data });
      return data;
    } catch (error) {
      setState({ loading: false, error: error.message, data: null });
      throw error;
    }
  }, []);
  return { ...state, run };
}
