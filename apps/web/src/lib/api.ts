"use client";

import { useCallback } from "react";
import useSWR, { type SWRConfiguration } from "swr";

import { useAuth } from "@/lib/auth";
import { API_URL } from "@/lib/config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  token: string | null,
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const isForm = init.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    method: init.method ?? "GET",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // FormData sets its own multipart boundary.
      ...(init.body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
    },
    body:
      init.body === undefined
        ? undefined
        : isForm
          ? (init.body as FormData)
          : JSON.stringify(init.body),
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // Domain errors use {error: {code, message}}; FastAPI validation errors use {detail}.
    const error = data?.error;
    const detail = Array.isArray(data?.detail) ? data.detail[0]?.msg : data?.detail;
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? detail ?? response.statusText,
    );
  }
  return data as T;
}

/** Imperative calls for mutations. */
export function useApi() {
  const { getToken } = useAuth();
  const call = useCallback(
    async <T>(path: string, init?: { method?: string; body?: unknown }) =>
      request<T>(await getToken(), path, init),
    [getToken],
  );
  return {
    get: <T>(path: string) => call<T>(path),
    post: <T>(path: string, body?: unknown) => call<T>(path, { method: "POST", body: body ?? {} }),
    patch: <T>(path: string, body: unknown) => call<T>(path, { method: "PATCH", body }),
    put: <T>(path: string, body: unknown) => call<T>(path, { method: "PUT", body }),
    upload: <T>(path: string, form: FormData) => call<T>(path, { method: "POST", body: form }),
    del: (path: string) => call<void>(path, { method: "DELETE" }),
  };
}

/** Cached reads. Pass null to skip fetching. */
export function useApiQuery<T>(path: string | null, config?: SWRConfiguration<T, ApiError>) {
  const { getToken, status } = useAuth();
  return useSWR<T, ApiError>(
    status === "signed-in" ? path : null,
    async (p: string) => request<T>(await getToken(), p),
    config,
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Algo deu errado. Tente novamente.";
}
