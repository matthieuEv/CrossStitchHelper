import { useState } from "react";

import { useT } from "../i18n";
import { MAX_LABEL_LENGTH, sameLabel, withLabel } from "../lib/labels";

interface LabelPickerProps {
  /** Labels currently given to the pattern. */
  labels: readonly string[];
  onChange: (labels: string[]) => void;
  /** Labels already used in the library, offered with one tap. */
  known: readonly string[];
}

/**
 * Picks a pattern's labels (issue #57): the chosen ones, each removable, the
 * library's other labels to add with one tap, and a field to create a new
 * one. Used on the import summary step and by the library's "Edit" action.
 */
export function LabelPicker({ labels, onChange, known }: LabelPickerProps) {
  const t = useT();
  const [draft, setDraft] = useState("");
  const suggestions = known.filter((label) => !labels.some((chosen) => sameLabel(chosen, label)));

  const addDraft = (): void => {
    onChange(withLabel(labels, draft, known));
    setDraft("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {labels.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {labels.map((label) => (
            <span key={label} className="label-tag">
              {label}
              <button
                type="button"
                className="label-tag-remove"
                aria-label={t("labels.remove", { label })}
                onClick={() => onChange(labels.filter((chosen) => chosen !== label))}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          style={{ flex: 1, minWidth: 0, minHeight: 44 }}
          value={draft}
          maxLength={MAX_LABEL_LENGTH}
          placeholder={t("labels.placeholder")}
          aria-label={t("labels.new")}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addDraft();
            }
          }}
        />
        <button
          type="button"
          className="btn btn-secondary"
          style={{ minHeight: 44, padding: "0 16px" }}
          disabled={draft.trim() === ""}
          onClick={addDraft}
        >
          {t("labels.add")}
        </button>
      </div>
      {suggestions.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {suggestions.map((label) => (
            <button
              key={label}
              type="button"
              className="label-tag label-tag-suggestion"
              aria-label={t("labels.addExisting", { label })}
              onClick={() => onChange(withLabel(labels, label, known))}
            >
              + {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
