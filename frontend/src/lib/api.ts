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

/**
 * Called when the server answers 401 on a route that needs a logged-in
 * profile (session expired, password reset by an admin, profile deleted):
 * `state/auth.tsx` goes back to the login screen. Never for `/auth/*`, where
 * a 401 is an expected answer (wrong password) handled by the caller.
 */
let unauthorizedListener: (() => void) | null = null;

export function setUnauthorizedListener(listener: (() => void) | null): void {
  unauthorizedListener = listener;
}

/**
 * Every call to the API goes through here. `X-CSH-Client` is what the server
 * checks on state-changing requests to tell its own frontend from a page of
 * another site riding on the session cookie (`backend/app/auth.py`,
 * Lot 10) — a cross-origin page cannot add a custom header.
 */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-CSH-Client", "web");
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (response.status === 401 && !path.startsWith("/auth/")) unauthorizedListener?.();
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw await errorFrom(response);
  }
  return (await response.json()) as T;
}

/** Same as `request`, for routes answering 204 (no body to parse). */
async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw await errorFrom(response);
  }
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

function deleteRequest(path: string, signal?: AbortSignal): Promise<void> {
  return requestNoContent(path, {
    method: "DELETE",
    ...(signal !== undefined && { signal }),
  });
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
  /** Labels the user sorts the library with (issue #57). */
  labels: string[];
  created_at: string;
  updated_at: string;
  /** The shared pattern this one is a copy of (Lot 11). */
  origin_pattern_id?: string | null;
  /** That shared pattern's content changed since it was copied. */
  update_available?: boolean;
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
  labels: string[];
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

/** A shade of the DMC colour chart (`GET /api/threads/dmc`, issue #39). */
export interface ApiThreadShade {
  code: string;
  name: string;
  rgb_hex: string;
}

export function fetchDmcShades(signal?: AbortSignal): Promise<ApiThreadShade[]> {
  return request<ApiThreadShade[]>("/threads/dmc", withSignal(signal));
}

export function fetchPatterns(signal?: AbortSignal): Promise<ApiPatternSummary[]> {
  return request<ApiPatternSummary[]>("/patterns", withSignal(signal));
}

/** Deletes a pattern and everything that belongs to it (issue #52). */
export function deletePattern(id: string): Promise<void> {
  return deleteRequest(`/patterns/${encodeURIComponent(id)}`);
}

/** Copies a pattern under `name`, with empty progress (issue #52). */
export function duplicatePattern(id: string, name: string): Promise<{ id: string }> {
  return postJson<{ id: string }>(`/patterns/${encodeURIComponent(id)}/duplicate`, { name });
}

/** The library's "Edit" action (issue #57): name and labels only. */
export function updatePattern(
  id: string,
  changes: { name?: string; labels?: string[] },
): Promise<ApiPatternDetail> {
  return patchJson<ApiPatternDetail>(`/patterns/${encodeURIComponent(id)}`, changes);
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

/** Cell layers the import wizard paints (issue #41). */
export type ApiImportStitch = "full" | "half" | "quarter";

export interface ApiImportFillZone {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  palette_index: number;
  /** Layer the area paints — `"full"` when absent (areas saved before #41). */
  stitch?: ApiImportStitch;
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
  /** 1/2 and 1/4 stitches detected in a type A PDF (Lot 9), same convention
   * as `detected_cells` — background under the `fills` of those layers. */
  detected_half: number[] | null;
  detected_quarter: number[] | null;
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
  /** Same encoding as `layer_full`, `null` when the layer has no stitch. */
  layer_half: string | null;
  layer_quarter: string | null;
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
  /** The personal pattern — null when imported into the shared library only. */
  pattern_id: string | null;
  shared_pattern_id: string | null;
}

/** Where an import goes (Lot 11): one's library, the shared one, or both. */
export type ApiLibraryChoice = "personal" | "shared" | "both";

export function commitImport(
  jobId: string,
  payload: {
    name: string;
    fabric_count?: number;
    labels?: string[];
    library?: ApiLibraryChoice;
    /** A paired host's shared library rather than this one's (Lot 11b). */
    shared_target_peer_id?: string | null;
  },
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
  /** 0 for a backup made before profiles (format version 1, Lot 10). */
  users_count: number;
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
export function restoreBackup(fileText: string): Promise<ApiBackupRestoreSummary> {
  return request<ApiBackupRestoreSummary>("/backup/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: fileText,
  });
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

// --- Profiles (Lot 10, issue #77) ------------------------------------------

export type ApiRole = "admin" | "user";

/** What the login screen shows about a profile — `ProfileCard` on the server. */
export interface ApiProfileCard {
  id: string;
  first_name: string;
  initials: string;
  /** 0-359, stable per profile: the avatar colour. */
  avatar_hue: number;
}

export interface ApiUser extends ApiProfileCard {
  email: string;
  last_name: string;
  role: ApiRole;
  created_at: string;
}

/** A profile as listed for admins, with the size of its personal library. */
export interface ApiAdminUser extends ApiUser {
  pattern_count: number;
}

export interface ApiAuthStatus {
  setup_required: boolean;
  user: ApiUser | null;
}

export interface ApiProfileFields {
  email: string;
  first_name: string;
  last_name: string;
}

export function fetchAuthStatus(signal?: AbortSignal): Promise<ApiAuthStatus> {
  return request<ApiAuthStatus>("/auth/status", withSignal(signal));
}

export function setupFirstAdmin(
  payload: ApiProfileFields & { password: string },
): Promise<ApiUser> {
  return postJson<ApiUser>("/auth/setup", payload);
}

export function fetchProfiles(signal?: AbortSignal): Promise<ApiProfileCard[]> {
  return request<ApiProfileCard[]>("/auth/profiles", withSignal(signal));
}

export function login(userId: string, password: string): Promise<ApiUser> {
  return postJson<ApiUser>("/auth/login", { user_id: userId, password });
}

export function logout(): Promise<void> {
  return requestNoContent("/auth/logout", { method: "POST" });
}

export function updateMe(changes: Partial<ApiProfileFields>): Promise<ApiUser> {
  return patchJson<ApiUser>("/auth/me", changes);
}

export function changeMyPassword(currentPassword: string, newPassword: string): Promise<void> {
  return requestNoContent("/auth/me/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function listUsers(signal?: AbortSignal): Promise<ApiAdminUser[]> {
  return request<ApiAdminUser[]>("/users", withSignal(signal));
}

export function createUser(
  payload: ApiProfileFields & { role: ApiRole; password: string },
): Promise<ApiAdminUser> {
  return postJson<ApiAdminUser>("/users", payload);
}

export function updateUser(
  userId: string,
  changes: Partial<ApiProfileFields> & { role?: ApiRole; password?: string },
): Promise<ApiAdminUser> {
  return patchJson<ApiAdminUser>(`/users/${userId}`, changes);
}

export function deleteUser(userId: string): Promise<void> {
  return deleteRequest(`/users/${userId}`);
}

// --- Shared library (Lot 11, issue #78) ------------------------------------

export interface ApiSharedPattern {
  id: string;
  name: string;
  width: number;
  height: number;
  palette_count: number;
  cell_count: number;
  labels: string[];
  revision: number;
  /** Null once the profile that added it has been deleted. */
  contributed_by_name: string | null;
  created_at: string;
  updated_at: string;
  /** The logged-in profile's copies of it. */
  my_copy_ids: string[];
  /** The paired instance this pattern's home is (Lot 11b); null if here. */
  source_name?: string | null;
  /** The logged-in profile may rename, replace or remove it. */
  can_moderate?: boolean;
}

/** A shared library a pattern can be added to: this instance's
 * (`peer_id` null), or a paired host's (Lot 11b). */
export interface ApiSharedTarget {
  peer_id: string | null;
  name: string;
}

export type ApiSharedRequestKind = "removal" | "replacement";
export type ApiSharedRequestStatus = "pending" | "accepted" | "rejected" | "cancelled";

export interface ApiSharedRequest {
  id: string;
  kind: ApiSharedRequestKind;
  status: ApiSharedRequestStatus;
  /** Null once the shared pattern is gone — `pattern_name` remains. */
  shared_pattern_id: string | null;
  pattern_name: string;
  requested_by_name: string | null;
  mine: boolean;
  message: string | null;
  /** For a pending replacement: the frozen proposed content. */
  proposal_pattern_id: string | null;
  created_at: string;
  resolved_at: string | null;
  /** The logged-in profile may accept or decline it (Lot 11b: not an admin
   * of an instance the request's home does not trust). */
  can_decide?: boolean;
}

export interface ApiSharedLibrary {
  patterns: ApiSharedPattern[];
  /** Every pending request for an admin; one's own, settled ones included. */
  requests: ApiSharedRequest[];
  targets?: ApiSharedTarget[];
}

export function fetchSharedLibrary(signal?: AbortSignal): Promise<ApiSharedLibrary> {
  return request<ApiSharedLibrary>("/shared", withSignal(signal));
}

/** A shared pattern, or a proposal (admins and its author). */
export function fetchSharedPatternDetail(id: string, signal?: AbortSignal): Promise<ApiPatternDetail> {
  return request<ApiPatternDetail>(`/shared/patterns/${encodeURIComponent(id)}`, withSignal(signal));
}

export function fetchSharedGrid(id: string, signal?: AbortSignal): Promise<ApiGrid> {
  return request<ApiGrid>(`/shared/patterns/${encodeURIComponent(id)}/grid`, withSignal(signal));
}

/** Copies a shared pattern into one's library under `name`. */
export function copySharedPattern(id: string, name: string): Promise<{ id: string }> {
  return postJson<{ id: string }>(`/shared/patterns/${encodeURIComponent(id)}/copy`, { name });
}

/** Puts a copy of one of my patterns in a shared library: this
 * instance's, or a paired host's (`targetPeerId`, Lot 11b). */
export function sharePattern(id: string, targetPeerId: string | null = null): Promise<{ id: string }> {
  return postJson<{ id: string }>(`/patterns/${encodeURIComponent(id)}/share`, {
    target_peer_id: targetPeerId,
  });
}

/** Brings a copy up to its shared original: in place, or as a new copy
 * named `name` when the progress would not survive (`in_place: false`). */
export function updateFromOrigin(
  id: string,
  name: string,
): Promise<{ pattern_id: string; in_place: boolean }> {
  return postJson<{ pattern_id: string; in_place: boolean }>(
    `/patterns/${encodeURIComponent(id)}/update-from-origin`,
    { name },
  );
}

/** Admins: rename a shared pattern, edit its labels. */
export function updateSharedPattern(
  id: string,
  changes: { name?: string; labels?: string[] },
): Promise<ApiPatternDetail> {
  return patchJson<ApiPatternDetail>(`/shared/patterns/${encodeURIComponent(id)}`, changes);
}

/** Admins: replace a shared pattern's content with one of their patterns. */
export function replaceSharedPattern(id: string, sourcePatternId: string): Promise<{ id: string }> {
  return postJson<{ id: string }>(`/shared/patterns/${encodeURIComponent(id)}/replace`, {
    source_pattern_id: sourcePatternId,
  });
}

/** Admins: remove a shared pattern (copies keep theirs). */
export function deleteSharedPattern(id: string): Promise<void> {
  return deleteRequest(`/shared/patterns/${encodeURIComponent(id)}`);
}

export function createSharedRequest(payload: {
  kind: ApiSharedRequestKind;
  shared_pattern_id: string;
  message?: string;
  proposal_pattern_id?: string;
}): Promise<ApiSharedRequest> {
  return postJson<ApiSharedRequest>("/shared/requests", payload);
}

export function settleSharedRequest(
  id: string,
  action: "accept" | "reject" | "cancel",
): Promise<ApiSharedRequest> {
  return postJson<ApiSharedRequest>(`/shared/requests/${encodeURIComponent(id)}/${action}`, {});
}

// --- Linking two instances (Lot 11b, issue #78) ---------------------------

export interface ApiPeer {
  id: string;
  name: string;
  /** "host": we mirror its shared library; "subscriber": it mirrors ours. */
  role: "host" | "subscriber";
  base_url: string | null;
  trust_admins: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface ApiInvitation {
  id: string;
  trust_admins: boolean;
  created_at: string;
  expires_at: string;
}

export interface ApiFederation {
  instance_id: string;
  instance_name: string;
  peers: ApiPeer[];
  invitations: ApiInvitation[];
}

export function fetchFederation(signal?: AbortSignal): Promise<ApiFederation> {
  return request<ApiFederation>("/federation", withSignal(signal));
}

export function renameInstance(name: string): Promise<void> {
  return requestNoContent("/federation/instance", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function createInvitation(
  publicUrl: string,
  trustAdmins: boolean,
): Promise<{ code: string; expires_at: string }> {
  return postJson<{ code: string; expires_at: string }>("/federation/invitations", {
    public_url: publicUrl,
    trust_admins: trustAdmins,
  });
}

export function withdrawInvitation(id: string): Promise<void> {
  return deleteRequest(`/federation/invitations/${encodeURIComponent(id)}`);
}

export function joinHost(code: string): Promise<ApiPeer> {
  return postJson<ApiPeer>("/federation/join", { code });
}

export function leavePeer(id: string): Promise<void> {
  return deleteRequest(`/federation/peers/${encodeURIComponent(id)}`);
}

/** Pull the paired hosts now (skipped by the server if done moments ago). */
export function syncShared(): Promise<{ synced: number; errors: string[] }> {
  return postJson<{ synced: number; errors: string[] }>("/federation/sync", {});
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
