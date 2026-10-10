import { useState } from "react";

import { useT } from "../i18n";
import { importPagePreviewUrl } from "../lib/api";
import { BackIcon } from "./Icons";

/** Zoom steps of the preview, as a multiple of the panel's width. */
const ZOOM_STEPS = [1, 1.5, 2, 3, 4, 6] as const;

interface SourcePreviewProps {
  jobId: string;
  pageCount: number;
  /** Page shown first — the one last looked at on the Cropping step. */
  initialPage: number;
}

/**
 * The imported file itself, shown on the Palette step next to the generated
 * grid (issue #40) so colours, symbols and stitch types can be checked
 * against the original. A plain raster preview of a page (the same one as on
 * the Cropping step), zoomed with buttons and panned by scrolling inside its
 * frame — no canvas: nothing is drawn or edited here.
 */
export function SourcePreview({ jobId, pageCount, initialPage }: SourcePreviewProps) {
  const t = useT();
  const [page, setPage] = useState(Math.min(Math.max(1, initialPage), pageCount));
  const [zoomIndex, setZoomIndex] = useState(0);
  const zoom = ZOOM_STEPS[zoomIndex] ?? 1;

  return (
    <section
      aria-label={t("import.source.title")}
      style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}
    >
      <div
        style={{ height: 320, borderRadius: 18, overflow: "auto", background: "var(--color-neutral-300)" }}
      >
        <img
          src={importPagePreviewUrl(jobId, page)}
          alt={t("import.source.alt", { page })}
          style={{ display: "block", width: `${zoom * 100}%`, maxWidth: "none", height: "auto" }}
        />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        {pageCount > 1 ? (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button
              type="button"
              className="btn btn-icon btn-ghost"
              aria-label={t("import.crop.prevPage")}
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              <BackIcon size={18} />
            </button>
            <span className="text-muted num" style={{ fontSize: 13, minWidth: "9ch", textAlign: "center" }}>
              {t("import.crop.page", { page, total: pageCount })}
            </span>
            <button
              type="button"
              className="btn btn-icon btn-ghost"
              aria-label={t("import.crop.nextPage")}
              disabled={page >= pageCount}
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            >
              <span style={{ display: "inline-flex", transform: "scaleX(-1)" }}>
                <BackIcon size={18} />
              </span>
            </button>
          </div>
        ) : (
          <span className="text-muted" style={{ fontSize: 12 }}>
            {t("import.source.title")}
          </span>
        )}
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label={t("import.source.zoomOut")}
            disabled={zoomIndex === 0}
            onClick={() => setZoomIndex((index) => Math.max(0, index - 1))}
          >
            −
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            aria-label={t("import.source.zoomIn")}
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            onClick={() => setZoomIndex((index) => Math.min(ZOOM_STEPS.length - 1, index + 1))}
          >
            +
          </button>
        </div>
      </div>
    </section>
  );
}
