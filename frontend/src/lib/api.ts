/**
 * Client de l'API locale.
 *
 * Toutes les requêtes sont relatives : le backend sert le frontend sur la même
 * origine, il n'y a donc aucune URL de serveur à configurer côté client — et
 * aucun appel vers un tiers n'est possible par construction.
 */

import { useEffect, useState } from "react";

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  schema_revision: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { Accept: "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(`Requête ${path} échouée`, response.status);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    // `exactOptionalPropertyTypes` refuse `signal: undefined` (incompatible
    // avec `AbortSignal | null` attendu par `RequestInit`) : on n'inclut la
    // propriété que si elle a une valeur.
    ...(signal !== undefined && { signal }),
  });
}

export function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

/** Formes des réponses de `/api/patterns/*` — voir `backend/app/schemas.py`. */
export interface ApiPaletteEntry {
  index_in_grid: number;
  brand: string;
  code: string;
  name: string;
  rgb_hex: string;
  symbol_key: string;
  symbol_svg: string | null;
  strands_full: number | null;
  strands_back: number | null;
  count_full: number;
  count_half: number;
  count_quarter: number;
  count_french: number;
  count_beads: number;
  backstitch_length_cm: number | null;
}

export interface ApiPatternSummary {
  id: string;
  name: string;
  width: number;
  height: number;
  palette_count: number;
  stitched_count: number;
  cell_count: number;
  percent: number;
  created_at: string;
  updated_at: string;
}

export interface ApiPatternDetail {
  id: string;
  owner_id: string | null;
  name: string;
  source_filename: string | null;
  fabric_count: number | null;
  width: number;
  height: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  palette: ApiPaletteEntry[];
}

export interface ApiGrid {
  pattern_id: string;
  width: number;
  height: number;
  encoding: string;
  version: number;
  layer_full: string;
  layer_half: string | null;
  layer_quarter: string | null;
  backstitch: Array<{ x1: number; y1: number; x2: number; y2: number; palette_index: number }>;
  french_knots: Array<{ x: number; y: number; palette_index: number }>;
}

export interface ApiProgress {
  pattern_id: string;
  version: number;
  stitched_count: number;
  cell_count: number;
  bitmap: string;
}

export interface ApiProgressOp {
  index: number;
  stitched: boolean;
}

export interface ApiProgressSyncResponse {
  version: number;
  stitched_count: number;
  conflict: boolean;
  missing_ops: ApiProgressOp[];
}

function withSignal(signal?: AbortSignal): RequestInit | undefined {
  return signal === undefined ? undefined : { signal };
}

export function fetchPatterns(signal?: AbortSignal): Promise<ApiPatternSummary[]> {
  return request<ApiPatternSummary[]>("/patterns", withSignal(signal));
}

export function fetchPatternDetail(id: string, signal?: AbortSignal): Promise<ApiPatternDetail> {
  return request<ApiPatternDetail>(`/patterns/${id}`, withSignal(signal));
}

export function fetchGrid(id: string, signal?: AbortSignal): Promise<ApiGrid> {
  return request<ApiGrid>(`/patterns/${id}/grid`, withSignal(signal));
}

export function fetchProgress(id: string, signal?: AbortSignal): Promise<ApiProgress> {
  return request<ApiProgress>(`/patterns/${id}/progress`, withSignal(signal));
}

export function syncProgress(
  id: string,
  baseVersion: number,
  ops: ApiProgressOp[],
  signal?: AbortSignal,
): Promise<ApiProgressSyncResponse> {
  return postJson<ApiProgressSyncResponse>(
    `/patterns/${id}/progress`,
    { base_version: baseVersion, ops },
    signal,
  );
}

export type ServerState = "checking" | "ok" | "unreachable";

/**
 * État de la liaison au serveur.
 *
 * L'application doit rester utilisable hors ligne : un serveur injoignable
 * n'est pas une erreur bloquante, seulement une information à afficher.
 */
export function useServerHealth(): { state: ServerState; health: HealthResponse | null } {
  const [state, setState] = useState<ServerState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((result) => {
        setHealth(result);
        setState("ok");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("unreachable");
      });
    return () => controller.abort();
  }, []);

  return { state, health };
}
