/**
 * Pattern labels (issue #57) — mirror of `backend/app/labels.py`: a label is
 * trimmed, its inner whitespace collapsed, and two labels differing only by
 * case are the same label.
 */

export const MAX_LABEL_LENGTH = 40;

export function cleanLabel(raw: string): string {
  return raw.trim().split(/\s+/).join(" ").slice(0, MAX_LABEL_LENGTH);
}

export function sameLabel(a: string, b: string): boolean {
  return a.toLocaleLowerCase() === b.toLocaleLowerCase();
}

/**
 * `labels` with `raw` added — spelled like an already `known` label when one
 * matches ignoring case, so typing "mini" reuses "Mini" rather than starting
 * a second label. Unchanged when `raw` is empty or already there.
 */
export function withLabel(
  labels: readonly string[],
  raw: string,
  known: readonly string[],
): string[] {
  const label = cleanLabel(raw);
  if (label === "" || labels.some((existing) => sameLabel(existing, label))) return [...labels];
  return [...labels, known.find((existing) => sameLabel(existing, label)) ?? label];
}

/** Every label used by `labelLists`, once each, sorted with `compare`. */
export function allLabels(
  labelLists: readonly (readonly string[] | undefined)[],
  compare: (a: string, b: string) => number,
): string[] {
  const result: string[] = [];
  for (const labels of labelLists) {
    for (const label of labels ?? []) {
      if (!result.some((existing) => sameLabel(existing, label))) result.push(label);
    }
  }
  return result.sort(compare);
}
