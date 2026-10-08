import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook for API calls with loading and error states
 * @param {function} apiFunc - API function to call (should return axios response)
 * @param {Array} deps - Dependencies array to trigger refetch
 * @param {boolean} immediate - Whether to fetch immediately on mount (default: true)
 * @returns {{ data: any, loading: boolean, error: string|null, refetch: function }}
 */
export default function useApi(apiFunc, deps = [], immediate = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);
  const funcRef = useRef(apiFunc);

  // Keep the latest apiFunc ref
  useEffect(() => {
    funcRef.current = apiFunc;
  }, [apiFunc]);

  const fetchData = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    try {
      const response = await funcRef.current(...args);
      if (mountedRef.current) {
        setData(response.data);
        setLoading(false);
      }
      return response.data;
    } catch (err) {
      if (mountedRef.current) {
        const message =
          err?.response?.data?.detail ||
          err?.response?.data?.message ||
          err?.message ||
          'An error occurred';
        setError(message);
        setLoading(false);
      }
      throw err;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (immediate) {
      fetchData();
    }
    return () => {
      mountedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refetch: fetchData };
}

/**
 * Hook for API mutations (POST, PUT, DELETE) - does not auto-fetch
 * @param {function} apiFunc - API function to call
 * @returns {{ mutate: function, data: any, loading: boolean, error: string|null }}
 */
export function useMutation(apiFunc) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const mutate = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);
      try {
        const response = await apiFunc(...args);
        if (mountedRef.current) {
          setData(response.data);
          setLoading(false);
        }
        return response.data;
      } catch (err) {
        if (mountedRef.current) {
          const message =
            err?.response?.data?.detail ||
            err?.response?.data?.message ||
            err?.message ||
            'An error occurred';
          setError(message);
          setLoading(false);
        }
        throw err;
      }
    },
    [apiFunc]
  );

  return { mutate, data, loading, error };
}
