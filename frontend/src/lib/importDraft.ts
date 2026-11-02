/**
 * Remembers, on this device, which import the wizard is in the middle of
 * (issue #102), so a page reload — or iOS Safari reloading a tab it had
 * evicted — reopens the wizard at the same step instead of an empty one.
 *
 * Only the pointer and what lives nowhere else: the crop, dimensions, palette
 * and painted areas are already saved on the import job by the server
 * (`PATCH /api/imports/{id}/config`), and are read back from it. Losing this
 * (private browsing, cleared site data) only means starting the import again.
 */

const STORAGE_KEY = "csh.importDraft";

export interface ImportDraft {
  jobId: string;
  /** Wizard step, 2 (crop) to 4 (recap) — step 1 has nothing to resume. */
  step: number;
  /** PDF page shown on the crop step. */
  page: number;
  /** Pattern name and fabric count, only sent to the server on commit. */
  name: string;
  fabricCount: string;
}

export function loadImportDraft(): ImportDraft | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { jobId, step, page, name, fabricCount } = parsed as Record<string, unknown>;
    if (
      typeof jobId !== "string" ||
      typeof step !== "number" ||
      !Number.isInteger(step) ||
      step < 2 ||
      step > 4 ||
      typeof page !== "number" ||
      !Number.isInteger(page) ||
      page < 1 ||
      typeof name !== "string" ||
      typeof fabricCount !== "string"
    ) {
      return null;
    }
    return { jobId, step, page, name, fabricCount };
  } catch {
    // Storage unavailable or corrupted value: nothing to resume.
    return null;
  }
}

export function saveImportDraft(draft: ImportDraft): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  } catch {
    // Storage unavailable (Safari private browsing, quota): best effort only.
  }
}

export function clearImportDraft(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: there was nothing to clear either.
  }
}
