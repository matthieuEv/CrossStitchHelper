/**
 * Local API client.
 *
 * All requests are relative: the backend serves the frontend on the same
 * origin, so there is no server URL to configure on the client — and no call
 * to a third party is possible by construction.
 */

import { useEffect, useState } from "react";

import type { Translate } from "../i18n";
import { fr, type TranslationKey } from "../i18n/fr";

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  schema_revision: string | null;
}

export type ApiErrorParams = Record<string, string | number>;

/**
 * A translatable API error — never a message already composed on the server
 * (translation audit, Lot 8): `code`/`params` mirror `ApiErrorDetail`
 * (`backend/app/schemas.py`) as is, to be translated in the component via
 * `translateApiError` when displayed (never here: this module has no access
 * to the language chosen by the user).
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly params: ApiErrorParams = {},
  ) {
    super(`Erreur API ${status} : ${code}`);
    this.name = "ApiError";
  }
}

/**
 * Translates an `ApiError` (or any other error) into a displayable message,
 * in the current language. `error.<code>` may be missing (server version
 * newer than the frontend's, unknown code): falls back to `error.unknown`
 * rather than crashing or showing a raw technical code.
 */
export function translateApiError(t: Translate, error: unknown): string {
  if (error instanceof ApiError) {
    const key = `error.${error.code}`;
    if (key in fr) return t(key as TranslationKey, error.params);
  }
  return t("error.unknown");
}

async function errorFrom(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (
      typeof detail === "object" &&
      detail !== null &&
      "code" in detail &&
      typeof (detail as { code: unknown }).code === "string"
    ) {
      const rawParams = (detail as { params?: unknown }).params;
      const params = (typeof rawParams === "object" && rawParams !== null ? rawParams : {}) as ApiErrorParams;
      return new ApiError(response.status, (detail as { code: string }).code, params);
    }
  } catch {
    // Non-JSON body (e.g. low-level network error, or a native FastAPI
    // validation error in a different shape): generic code below.
  }
  return new ApiError(response.status, "unknown");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { Accept: "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw await errorFrom(response);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    // `exactOptionalPropertyTypes` rejects `signal: undefined` (incompatible
    // with the `AbortSignal | null` expected by `RequestInit`): the property
    // is only included if it has a value.
    ...(signal !== undefined && { signal }),
  });
}

function patchJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...(signal !== undefined && { signal }),
  });
}

async function deleteRequest(path: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`/api${path}`, {
    method: "DELETE",
    ...(signal !== undefined && { signal }),
  });
  if (!response.ok) {
    throw await errorFrom(response);
  }
}

export function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

/** Shapes of the `/api/patterns/*` responses — see `backend/app/schemas.py`. */
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

/** Same enumeration as `backend/app/schemas.py::ProgressOp.layer` (Lot 8) —
 * never an index space shared between categories. */
export type ApiStitchLayer = "full" | "half" | "quarter" | "backstitch" | "knot";

export interface ApiProgress {
  pattern_id: string;
  version: number;
  stitched_count: number;
  cell_count: number;
  bitmap: string;
  /** Checked 1/2 stitches (Lot 8), same shape as `bitmap` — `null` if the
   * pattern has no 1/2 content (`ApiGrid.layer_half` absent). */
  bitmap_half: string | null;
  bitmap_quarter: string | null;
  /** 1 bit per element of `ApiGrid.backstitch`/`french_knots`, not per cell —
   * `null` if the corresponding list is empty. */
  bitmap_backstitch: string | null;
  bitmap_knots: string | null;
  stitched_count_half: number;
  stitched_count_quarter: number;
  stitched_count_backstitch: number;
  stitched_count_knots: number;
}

export interface ApiProgressOp {
  /** Defaults to "full" on the server if omitted (backward compatibility) —
   * always provided explicitly by the client since Lot 8. */
  layer: ApiStitchLayer;
  index: number;
  stitched: boolean;
}

export interface ApiProgressSyncResponse {
  version: number;
  stitched_count: number;
  conflict: boolean;
  missing_ops: ApiProgressOp[];
}

export interface ApiActivityDay {
  weekday: number;
  stitches: number;
}

export interface ApiActivitySession {
  hours_ago: number;
  stitches: number;
  minutes: number;
}

export interface ApiPatternActivity {
  activity: ApiActivityDay[];
  sessions: ApiActivitySession[];
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

/** Open, documented format (specification §6.4) — a direct link is enough. */
export function patternExportUrl(id: string): string {
  return `/api/patterns/${id}/export`;
}

export function fetchPatternActivity(
  id: string,
  signal?: AbortSignal,
): Promise<ApiPatternActivity> {
  return request<ApiPatternActivity>(`/patterns/${id}/activity`, withSignal(signal));
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

/** Shapes of the `/api/imports/*` responses — see `backend/app/schemas.py`. */
export interface ApiImportCrop {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface ApiImportPaletteEntry {
  code: string;
  name: string;
  rgb_hex: string;
  symbol_key: string;
  /** Real symbol cut out of the PDF (Lot 4) — see `ApiPaletteEntry`. */
  symbol_svg?: string | null;
}

export interface ApiImportFillZone {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  palette_index: number;
}

export interface ApiImportConfig {
  /** Manual cropping by page number (str key), a purely visual aid — see
   * `backend/app/schemas.py::ImportConfig.crop_by_page`. */
  crop_by_page: Record<string, ApiImportCrop>;
  columns: number | null;
  rows: number | null;
  palette: ApiImportPaletteEntry[];
  fills: ApiImportFillZone[];
  /** Automatically detected grid (Lot 4), background under `fills` — see `apply_fills`. */
  detected_cells: number[] | null;
  /** Indices into `detected_cells` of the cells flagged uncertain by type
   * B/C detection (Lot 5) — doubtful colour and/or ambiguous symbol, never a
   * wrong cell left without indication. */
  uncertain_cells: number[] | null;
  /** Fabric count read from the PDF (type A, Lot 9) — pre-fills the Summary
   * screen's field, never imposed: manual input always wins, see
   * `manualFabricEditRef` in `ImportScreen.tsx`. */
  detected_fabric_count: number | null;
}

export interface ApiImportConfigPatch {
  crop_by_page?: Record<string, ApiImportCrop>;
  columns?: number;
  rows?: number;
  palette?: ApiImportPaletteEntry[];
  fills?: ApiImportFillZone[];
  detected_cells?: number[] | null;
  uncertain_cells?: number[] | null;
}

export interface ApiDetectionWarning {
  code: string;
  params: ApiErrorParams;
}

export interface ApiImportDetection {
  grid_type: string;
  confidence: number;
  warnings: ApiDetectionWarning[];
}

/**
 * Translates an automatic detection warning — same principle as
 * `translateApiError` (key `import.warning.<code>` rather than
 * `error.<code>`, falling back to `import.warning.unknown`).
 */
export function translateDetectionWarning(t: Translate, warning: ApiDetectionWarning): string {
  const key = `import.warning.${warning.code}`;
  if (key in fr) return t(key as TranslationKey, warning.params);
  return t("import.warning.unknown");
}

export interface ApiImportPreview {
  width: number;
  height: number;
  cell_count: number;
  filled_count: number;
  layer_full: string;
  palette: ApiImportPaletteEntry[];
}

/** Recipe (Lot 6) whose `crop_by_page` pre-filled this job — see `ApiRecipe`. */
export interface ApiAppliedRecipe {
  id: string;
  label: string;
}

export interface ApiImportJob {
  id: string;
  status: "ready" | "committed";
  kind: "pdf" | "image";
  page_count: number;
  source_filename: string;
  pattern_id: string | null;
  config: ApiImportConfig;
  preview: ApiImportPreview | null;
  detection: ApiImportDetection | null;
  detecting: boolean;
  applied_recipe: ApiAppliedRecipe | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export function createImport(file: File, signal?: AbortSignal): Promise<ApiImportJob> {
  const body = new FormData();
  body.append("file", file);
  return request<ApiImportJob>("/imports", {
    method: "POST",
    body,
    ...(signal !== undefined && { signal }),
  });
}

export function fetchImport(jobId: string, signal?: AbortSignal): Promise<ApiImportJob> {
  return request<ApiImportJob>(`/imports/${jobId}`, withSignal(signal));
}

export function importPagePreviewUrl(jobId: string, pageNumber: number): string {
  return `/api/imports/${jobId}/pages/${pageNumber}/preview`;
}

export function patchImportConfig(
  jobId: string,
  patch: ApiImportConfigPatch,
  signal?: AbortSignal,
): Promise<ApiImportJob> {
  return patchJson<ApiImportJob>(`/imports/${jobId}/config`, patch, signal);
}

export function extractImport(jobId: string, signal?: AbortSignal): Promise<ApiImportJob> {
  return postJson<ApiImportJob>(`/imports/${jobId}/extract`, {}, signal);
}

export interface ApiImportCommitResponse {
  pattern_id: string;
}

export function commitImport(
  jobId: string,
  payload: { name: string; fabric_count?: number },
  signal?: AbortSignal,
): Promise<ApiImportCommitResponse> {
  return postJson<ApiImportCommitResponse>(`/imports/${jobId}/commit`, payload, signal);
}

/**
 * Reusable recipe library (Lot 6, specification §8.7).
 *
 * `config` only carries `crop_by_page` — never a pattern's dimensions or
 * palette, which are its creative content (see
 * `backend/app/models.py::Recipe`).
 */
export interface ApiRecipe {
  id: string;
  fingerprint: string;
  label: string;
  grid_type: string;
  config: { crop_by_page: Record<string, ApiImportCrop> };
  created_at: string;
  usage_count: number;
}

export function listRecipes(signal?: AbortSignal): Promise<ApiRecipe[]> {
  return request<ApiRecipe[]>("/recipes", withSignal(signal));
}

export function createRecipe(
  jobId: string,
  label: string,
  signal?: AbortSignal,
): Promise<ApiRecipe> {
  return postJson<ApiRecipe>("/recipes", { job_id: jobId, label }, signal);
}

export function deleteRecipe(recipeId: string, signal?: AbortSignal): Promise<void> {
  return deleteRequest(`/recipes/${recipeId}`, signal);
}

// --- Full backup/restore (Lot 8, specification §7.5) -----------------------

export interface ApiBackupRestoreSummary {
  patterns_count: number;
  recipes_count: number;
  progress_events_count: number;
}

/** Open (JSON), documented format (§7.5) — like `patternExportUrl`, a direct
 * link is enough: the server already sets the download header. */
export function backupExportUrl(): string {
  return "/api/backup";
}

/**
 * Full restore: replaces all existing data with the contents of `fileText`
 * (the raw text of a file exported via `backupExportUrl`). Goes through
 * `fetch` directly rather than `postJson`: `fileText` is already the
 * serialised JSON to send as is, `postJson` would serialise it a second time
 * (`JSON.stringify` of a string that is already JSON).
 */
export async function restoreBackup(fileText: string): Promise<ApiBackupRestoreSummary> {
  const response = await fetch("/api/backup/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: fileText,
  });
  if (!response.ok) {
    throw await errorFrom(response);
  }
  return (await response.json()) as ApiBackupRestoreSummary;
}

export interface ApiAutoBackupSettings {
  enabled: boolean;
}

export function fetchAutoBackupSetting(
  signal?: AbortSignal,
): Promise<ApiAutoBackupSettings> {
  return request<ApiAutoBackupSettings>("/backup/auto", withSignal(signal));
}

export function setAutoBackupSetting(
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ApiAutoBackupSettings> {
  return request<ApiAutoBackupSettings>("/backup/auto", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
    ...(signal !== undefined && { signal }),
  });
}

export type ServerState = "checking" | "ok" | "unreachable";

/**
 * State of the connection to the server.
 *
 * The application must remain usable offline: an unreachable server is not a
 * blocking error, just information to display.
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
