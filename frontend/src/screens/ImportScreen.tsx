import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { ImportGridPainter } from "../components/ImportGridPainter";
import { BackIcon, UploadIcon } from "../components/Icons";
import { PatternThumbnail } from "../components/PatternThumbnail";
import { useT } from "../i18n";
import { useWideLayout } from "../lib/hooks";
import {
  commitImport,
  createImport,
  createRecipe,
  extractImport,
  fetchImport,
  importPagePreviewUrl,
  patchImportConfig,
  translateApiError,
  translateDetectionWarning,
  type ApiImportConfig,
  type ApiImportFillZone,
  type ApiImportJob,
  type ApiImportPaletteEntry,
} from "../lib/api";
import { patternFromImportPreview } from "../lib/mappers";
import { useImportPainter } from "../state/useImportPainter";

type Edge = "left" | "top" | "right" | "bottom";
interface Crop {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const STEP_COUNT = 4;
const MAX_INSET = 45;
const DEFAULT_CROP: Crop = { left: 4, top: 4, right: 4, bottom: 4 };

/** Starting palette, purely so the painting step does not open empty. */
function nextPaletteEntry(existing: readonly ApiImportPaletteEntry[]): ApiImportPaletteEntry {
  const hues = ["#8a5b9b", "#b35b6b", "#5b8f6f", "#5b7bb3", "#b38a5b", "#5b5b5b"];
  const hex = hues[existing.length % hues.length] ?? "#5b5b5b";
  return { code: "", name: "", rgb_hex: hex, symbol_key: String((existing.length % 9) + 1) };
}

interface ImportScreenProps {
  onCancel: () => void;
  onFinish: (patternId: string) => void;
}

export function ImportScreen({ onCancel, onFinish }: ImportScreenProps) {
  const t = useT();
  const wide = useWideLayout();

  const [step, setStep] = useState(1);
  const [job, setJob] = useState<ApiImportJob | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // An independent crop per page — see `import.crop.hint` and
  // `backend/app/schemas.py::ImportConfig.crop_by_page`: one page may contain
  // the legend, another the grid, so a single crop imposed on every page
  // would make no sense.
  const [cropByPage, setCropByPage] = useState<Record<number, Crop>>({});
  const [page, setPage] = useState(1);
  const [columns, setColumns] = useState<string>("");
  const [rows, setRows] = useState<string>("");
  const [palette, setPalette] = useState<ApiImportPaletteEntry[]>([]);
  const [fills, setFills] = useState<ApiImportFillZone[]>([]);
  const [detectedCells, setDetectedCells] = useState<number[] | null>(null);
  const [uncertainCells, setUncertainCells] = useState<number[] | null>(null);
  const [detection, setDetection] = useState<ApiImportJob["detection"]>(null);
  const [activeIndex, setActiveIndex] = useState(1);

  const [name, setName] = useState("");
  const [fabricCount, setFabricCount] = useState("14");
  const [preview, setPreview] = useState<ApiImportJob["preview"] | null>(null);
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const [saveAsRecipe, setSaveAsRecipe] = useState(false);
  const [recipeLabel, setRecipeLabel] = useState("");
  const [recipeError, setRecipeError] = useState<string | null>(null);

  const stageRef = useRef<HTMLDivElement>(null);
  const dragEdgeRef = useRef<Edge | null>(null);
  /** Becomes `true` as soon as the user types their own dimensions — no
   * detection poll may then overwrite their input. */
  const manualEditRef = useRef(false);
  /** Same principle as `manualEditRef`, but for the fabric count alone
   * (Lot 9) — the two are independent: correcting the dimensions must not
   * freeze the detected fabric count, and vice versa. */
  const manualFabricEditRef = useRef(false);

  const stepLabels = [
    t("import.step.file"),
    t("import.step.crop"),
    t("import.step.palette"),
    t("import.step.recap"),
  ];

  const applyConfig = (config: ApiImportConfig): void => {
    setCropByPage(
      Object.fromEntries(
        Object.entries(config.crop_by_page).map(([pageNumber, pageCrop]) => [
          Number(pageNumber),
          pageCrop,
        ]),
      ),
    );
    if (config.columns !== null) setColumns(String(config.columns));
    if (config.rows !== null) setRows(String(config.rows));
    setPalette(config.palette);
    setFills(config.fills);
    setDetectedCells(config.detected_cells);
    setUncertainCells(config.uncertain_cells);
    if (!manualFabricEditRef.current && config.detected_fabric_count !== null) {
      setFabricCount(String(config.detected_fabric_count));
    }
  };

  const upload = async (file: File): Promise<void> => {
    setUploading(true);
    setUploadError(null);
    try {
      const created = await createImport(file);
      manualEditRef.current = false;
      manualFabricEditRef.current = false;
      setJob(created);
      applyConfig(created.config);
      setDetection(created.detection);
      setName(file.name.replace(/\.(pdf|png|jpe?g)$/i, ""));
      setPage(1);
      setStep(2);
    } catch (error) {
      setUploadError(translateApiError(t, error));
    } finally {
      setUploading(false);
    }
  };

  // Automatic detection (Lot 4): runs as a background task on the server —
  // poll until it has finished, never overwriting manual input that has
  // already started (`manualEditRef`).
  useEffect(() => {
    if (job === null || !job.detecting) return;
    const jobId = job.id;
    let cancelled = false;
    const timer = setInterval(() => {
      void fetchImport(jobId).then((updated) => {
        if (cancelled) return;
        setJob(updated);
        if (!manualEditRef.current) {
          applyConfig(updated.config);
          setDetection(updated.detection);
        }
      });
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.detecting]);

  const onFileChosen = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file !== undefined) void upload(file);
  };

  const startDrag = (edge: Edge) => (event: ReactPointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    dragEdgeRef.current = edge;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const edge = dragEdgeRef.current;
      const stage = stageRef.current;
      if (edge === null || stage === null) return;

      const box = stage.getBoundingClientRect();
      const x = ((event.clientX - box.left) / box.width) * 100;
      const y = ((event.clientY - box.top) / box.height) * 100;
      const clamp = (value: number): number => Math.max(0, Math.min(MAX_INSET, value));

      setCropByPage((current) => {
        const currentCrop = current[page] ?? DEFAULT_CROP;
        const nextCrop = (() => {
          switch (edge) {
            case "left":
              return { ...currentCrop, left: clamp(x) };
            case "right":
              return { ...currentCrop, right: clamp(100 - x) };
            case "top":
              return { ...currentCrop, top: clamp(y) };
            case "bottom":
              return { ...currentCrop, bottom: clamp(100 - y) };
          }
        })();
        return { ...current, [page]: nextCrop };
      });
    },
    [page],
  );

  const endDrag = useCallback(() => {
    dragEdgeRef.current = null;
  }, []);

  const crop = cropByPage[page] ?? DEFAULT_CROP;
  const centerX = `${crop.left + (100 - crop.left - crop.right) / 2}%`;
  const centerY = `${crop.top + (100 - crop.top - crop.bottom) / 2}%`;

  const columnsValue = Number.parseInt(columns, 10);
  const rowsValue = Number.parseInt(rows, 10);
  const dimensionsValid =
    Number.isFinite(columnsValue) && columnsValue > 0 && Number.isFinite(rowsValue) && rowsValue > 0;

  const goToPalette = async (): Promise<void> => {
    if (job === null || !dimensionsValid) return;
    const cropByPageForApi = Object.fromEntries(
      Object.entries(cropByPage).map(([pageNumber, pageCrop]) => [String(pageNumber), pageCrop]),
    );
    const updated = await patchImportConfig(job.id, {
      crop_by_page: cropByPageForApi,
      columns: columnsValue,
      rows: rowsValue,
    });
    setJob(updated);
    setStep(3);
  };

  // Filtered to the current range: `uncertainCells` refers to the dimensions
  // at detection time, stale as soon as the user types others by hand before
  // the next server round trip (same risk as `detectedCells`, see
  // `applyFillsLocal` on the painting side).
  const uncertainCellsSet = useMemo(() => {
    if (uncertainCells === null || !dimensionsValid) return null;
    const bound = columnsValue * rowsValue;
    const filtered = uncertainCells.filter((index) => index >= 0 && index < bound);
    return filtered.length > 0 ? new Set(filtered) : null;
  }, [uncertainCells, dimensionsValid, columnsValue, rowsValue]);

  const painter = useImportPainter(
    dimensionsValid ? columnsValue : 0,
    dimensionsValid ? rowsValue : 0,
    palette.map((entry) => ({
      code: entry.code,
      name: entry.name,
      hex: entry.rgb_hex,
      symbol: entry.symbol_key,
      ...(entry.symbol_svg !== null &&
        entry.symbol_svg !== undefined && { symbolSvg: entry.symbol_svg }),
    })),
    fills,
    (nextFills) => {
      setFills(nextFills);
      if (job !== null) void patchImportConfig(job.id, { fills: nextFills });
    },
    name,
    detectedCells,
  );

  const addPaletteEntry = (): void => {
    const next = [...palette, nextPaletteEntry(palette)];
    setPalette(next);
    setActiveIndex(next.length);
    if (job !== null) void patchImportConfig(job.id, { palette: next });
  };

  const updatePaletteEntry = (index: number, patch: Partial<ApiImportPaletteEntry>): void => {
    const next = palette.map((entry, i) => (i === index ? { ...entry, ...patch } : entry));
    setPalette(next);
  };

  const commitPaletteEdits = (): void => {
    if (job !== null) void patchImportConfig(job.id, { palette });
  };

  const removePaletteEntry = (index: number): void => {
    const next = palette.filter((_, i) => i !== index);
    setPalette(next);
    if (activeIndex > next.length) setActiveIndex(Math.max(1, next.length));
    if (job !== null) void patchImportConfig(job.id, { palette: next });
  };

  const goToRecap = async (): Promise<void> => {
    if (job === null) return;
    const updated = await extractImport(job.id);
    setJob(updated);
    setPreview(updated.preview);
    setStep(4);
  };

  const finish = async (): Promise<void> => {
    if (job === null || name.trim() === "") return;
    setCommitting(true);
    setCommitError(null);
    setRecipeError(null);
    try {
      if (saveAsRecipe && recipeLabel.trim() !== "") {
        try {
          await createRecipe(job.id, recipeLabel.trim());
        } catch (error) {
          // A failed recipe must never prevent creating the pattern — it is a
          // convenience for next time, not a required step.
          setRecipeError(translateApiError(t, error));
        }
      }
      const fabric = Number.parseInt(fabricCount, 10);
      const response = await commitImport(job.id, {
        name: name.trim(),
        ...(Number.isFinite(fabric) && fabric > 0 && { fabric_count: fabric }),
      });
      onFinish(response.pattern_id);
    } catch (error) {
      setCommitError(translateApiError(t, error));
    } finally {
      setCommitting(false);
    }
  };

  const previewPattern = preview !== null ? patternFromImportPreview(preview, name) : null;

  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div style={{ flex: "none", padding: "18px 20px 14px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            marginBottom: 14,
          }}
        >
          <h3 style={{ margin: 0 }}>{t("import.title")}</h3>
          <button type="button" className="btn btn-ghost" style={{ minHeight: 44 }} onClick={onCancel}>
            {t("import.cancel")}
          </button>
        </div>

        <ol style={{ display: "flex", gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
          {stepLabels.map((label, index) => {
            const position = index + 1;
            const reached = position <= step;
            return (
              <li key={label} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                <div
                  style={{
                    height: 6,
                    borderRadius: 999,
                    background: reached
                      ? "var(--color-accent)"
                      : "color-mix(in srgb, var(--color-text) 14%, transparent)",
                  }}
                />
                <div
                  style={{
                    fontSize: 11,
                    color:
                      position === step
                        ? "var(--color-accent)"
                        : "color-mix(in srgb, var(--color-text) 55%, transparent)",
                  }}
                >
                  {label}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "6px 20px 20px" }}>
        {step === 1 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="dropzone">
              <UploadIcon size={40} />
              <div style={{ fontFamily: "var(--font-heading)", fontSize: 19, margin: "12px 0 6px" }}>
                {t("import.drop.title")}
              </div>
              <p className="text-muted" style={{ fontSize: 13, maxWidth: "34ch", margin: "0 auto 16px" }}>
                {t("import.drop.hint")}
              </p>
              <label className="btn btn-secondary" style={{ minHeight: 44, padding: "0 18px" }}>
                {uploading ? t("import.drop.uploading") : t("import.drop.choose")}
                <input
                  type="file"
                  accept="application/pdf,image/png,image/jpeg"
                  style={{ display: "none" }}
                  disabled={uploading}
                  onChange={onFileChosen}
                />
              </label>
            </div>
            {uploadError !== null && (
              <p className="tag tag-accent" style={{ margin: 0 }}>
                {t("import.drop.error", { message: uploadError })}
              </p>
            )}
          </div>
        )}

        {step === 2 && job !== null && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {job.detecting
                ? t("import.crop.hintDetecting")
                : detectedCells !== null
                  ? t("import.crop.hintDetected")
                  : t("import.crop.hint")}
            </div>

            {job.applied_recipe !== null && (
              <div
                className="tag tag-accent"
                style={{ margin: 0, alignSelf: "flex-start" }}
              >
                {t("import.detection.recipeApplied", { label: job.applied_recipe.label })}
              </div>
            )}

            {detection !== null && (
              <div
                style={{
                  padding: "12px 16px",
                  borderRadius: 18,
                  background: "var(--color-surface)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {t("import.detection.title", {
                    type: detection.grid_type,
                    confidence: Math.round(detection.confidence * 100),
                  })}
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  {t("import.detection.hint")}
                </div>
                {detectedCells !== null && job.page_count > 1 && (
                  <div className="text-muted" style={{ fontSize: 12 }}>
                    {t("import.detection.multiPage", { pageCount: job.page_count })}
                  </div>
                )}
                {detection.warnings.map((warning, index) => (
                  <div key={index} className="text-faint" style={{ fontSize: 11 }}>
                    ⚠ {translateDetectionWarning(t, warning)}
                  </div>
                ))}
              </div>
            )}

            {job.page_count > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14 }}>
                <button
                  type="button"
                  className="btn btn-icon btn-ghost"
                  aria-label={t("import.crop.prevPage")}
                  disabled={page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  <BackIcon size={18} />
                </button>
                <span className="text-muted num" style={{ fontSize: 13, minWidth: "10ch", textAlign: "center" }}>
                  {t("import.crop.page", { page, total: job.page_count })}
                </span>
                <button
                  type="button"
                  className="btn btn-icon btn-ghost"
                  aria-label={t("import.crop.nextPage")}
                  disabled={page >= job.page_count}
                  onClick={() => setPage((current) => Math.min(job.page_count, current + 1))}
                >
                  <span style={{ display: "inline-flex", transform: "scaleX(-1)" }}>
                    <BackIcon size={18} />
                  </span>
                </button>
              </div>
            )}

            <div
              ref={stageRef}
              className="crop-stage"
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerLeave={endDrag}
            >
              <img
                key={page}
                src={importPagePreviewUrl(job.id, page)}
                alt=""
                style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
              />
              {detectedCells === null && !job.detecting && (
                <>
                  <div
                    style={{
                      position: "absolute",
                      left: `${crop.left}%`,
                      top: `${crop.top}%`,
                      right: `${crop.right}%`,
                      bottom: `${crop.bottom}%`,
                      border: "2px solid var(--color-accent)",
                      borderRadius: 6,
                      boxShadow: "0 0 0 9999px rgba(20, 16, 12, 0.44)",
                    }}
                  />
                  {(["top", "bottom", "left", "right"] as const).map((edge) => (
                    <div
                      key={edge}
                      className="crop-handle"
                      onPointerDown={startDrag(edge)}
                      style={{
                        ...(edge === "top" || edge === "bottom"
                          ? { left: centerX, width: 64, height: 44, cursor: "ns-resize" }
                          : { top: centerY, width: 44, height: 64, cursor: "ew-resize" }),
                        ...(edge === "top" && {
                          top: `${crop.top}%`,
                          transform: "translate(-50%, -50%)",
                        }),
                        ...(edge === "bottom" && {
                          bottom: `${crop.bottom}%`,
                          transform: "translate(-50%, 50%)",
                        }),
                        ...(edge === "left" && {
                          left: `${crop.left}%`,
                          transform: "translate(-50%, -50%)",
                        }),
                        ...(edge === "right" && {
                          right: `${crop.right}%`,
                          transform: "translate(50%, -50%)",
                        }),
                      }}
                    >
                      <span
                        style={
                          edge === "top" || edge === "bottom"
                            ? { width: 52, height: 8 }
                            : { width: 8, height: 52 }
                        }
                      />
                    </div>
                  ))}
                </>
              )}
              {job.detecting && (
                <div className="crop-stage-loading">
                  <div className="spinner" role="status" aria-label={t("import.detection.running")} />
                  <div style={{ fontSize: 13 }}>{t("import.detection.running")}</div>
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <label style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {t("import.crop.columns")}
                </span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={columns}
                  onChange={(event) => {
                    manualEditRef.current = true;
                    setColumns(event.target.value.replace(/[^0-9]/g, ""));
                  }}
                  style={{ minHeight: 46 }}
                />
              </label>
              <label style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {t("import.crop.rows")}
                </span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={rows}
                  onChange={(event) => {
                    manualEditRef.current = true;
                    setRows(event.target.value.replace(/[^0-9]/g, ""));
                  }}
                  style={{ minHeight: 46 }}
                />
              </label>
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("import.paint.hint")}
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              {palette.map((entry, index) => (
                <button
                  key={index}
                  type="button"
                  className="badge"
                  aria-pressed={activeIndex === index + 1}
                  onClick={() => setActiveIndex(index + 1)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    border:
                      activeIndex === index + 1
                        ? "2px solid var(--color-accent)"
                        : "2px solid transparent",
                  }}
                >
                  <span
                    className="swatch"
                    style={{ width: 18, height: 18, background: entry.rgb_hex }}
                  />
                  {entry.symbol_svg !== null && entry.symbol_svg !== undefined && (
                    // Real symbol cut out of the PDF (Lot 4) — see
                    // `ColorList.tsx` for the same principle in Tracking.
                    <img
                      src={`data:image/svg+xml;base64,${btoa(entry.symbol_svg)}`}
                      alt=""
                      style={{ width: 16, height: 16 }}
                    />
                  )}
                  {entry.code || entry.name || "—"}
                </button>
              ))}
              <button
                type="button"
                className="badge"
                aria-pressed={activeIndex === 0}
                onClick={() => setActiveIndex(0)}
              >
                🧹 {t("import.paint.eraser")}
              </button>
              <button type="button" className="btn btn-ghost" style={{ minHeight: 32 }} onClick={addPaletteEntry}>
                + {t("import.palette.add")}
              </button>
            </div>

            {palette.length === 0 ? (
              <p className="text-muted" style={{ fontSize: 13 }}>
                {t("import.palette.empty")}
              </p>
            ) : (
              <ImportGridPainter
                painter={painter}
                activeIndex={activeIndex}
                uncertainCells={uncertainCellsSet}
              />
            )}

            {uncertainCellsSet !== null && (
              <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>
                {t("import.paint.uncertainHint", { count: uncertainCellsSet.size })}
              </p>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: wide ? "repeat(2, 1fr)" : "1fr",
                gap: 8,
              }}
            >
              {palette.map((entry, index) => {
                const hasRealSymbol = entry.symbol_svg !== null && entry.symbol_svg !== undefined;
                return (
                  <div
                    key={index}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 10px",
                      borderRadius: 14,
                      background:
                        activeIndex === index + 1 ? "var(--color-surface)" : "transparent",
                    }}
                  >
                    <input
                      type="color"
                      value={entry.rgb_hex}
                      onChange={(event) => updatePaletteEntry(index, { rgb_hex: event.target.value })}
                      onBlur={commitPaletteEdits}
                      style={{ width: 34, height: 34, flex: "none", border: 0, background: "none" }}
                      aria-label={t("import.legend.color")}
                    />
                    {hasRealSymbol ? (
                      // Real symbol cut out of the PDF (Lot 4): the internal
                      // key (`symbol_key`) then no longer needs to be visible or
                      // editable — this symbol comes from the file, never from
                      // it.
                      <img
                        src={`data:image/svg+xml;base64,${btoa(entry.symbol_svg as string)}`}
                        alt=""
                        style={{ width: 28, height: 28, flex: "none" }}
                      />
                    ) : (
                      <input
                        className="input"
                        style={{ width: 44, textAlign: "center", flex: "none" }}
                        maxLength={2}
                        placeholder={t("import.legend.symbol")}
                        value={entry.symbol_key}
                        onChange={(event) =>
                          updatePaletteEntry(index, { symbol_key: event.target.value })
                        }
                        onBlur={commitPaletteEdits}
                      />
                    )}
                    <input
                      className="input"
                      style={{ width: 90 }}
                      placeholder={t("import.legend.code")}
                      value={entry.code}
                      onChange={(event) => updatePaletteEntry(index, { code: event.target.value })}
                      onBlur={commitPaletteEdits}
                    />
                    <input
                      className="input"
                      style={{ flex: 1, minWidth: 0 }}
                      placeholder={t("import.legend.name")}
                      value={entry.name}
                      onChange={(event) => updatePaletteEntry(index, { name: event.target.value })}
                      onBlur={commitPaletteEdits}
                    />
                    <button
                      type="button"
                      className="btn btn-icon btn-ghost"
                      aria-label={t("import.palette.remove")}
                      onClick={() => removePaletteEntry(index)}
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {step === 4 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {previewPattern === null ? (
              <p className="tag tag-accent" style={{ margin: 0 }}>
                {t("import.recap.incomplete")}
              </p>
            ) : (
              <>
                <div
                  style={{
                    borderRadius: 22,
                    overflow: "hidden",
                    background: "var(--color-neutral-200)",
                    aspectRatio: "1.4",
                  }}
                >
                  <PatternThumbnail pattern={previewPattern} progress={null} label={name} />
                </div>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span className="text-muted" style={{ fontSize: 12 }}>
                    {t("import.recap.name")}
                  </span>
                  <input
                    className="input"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    style={{ minHeight: 46 }}
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 160 }}>
                  <span className="text-muted" style={{ fontSize: 12 }}>
                    {t("import.recap.fabric")}
                  </span>
                  <input
                    className="input"
                    inputMode="numeric"
                    value={fabricCount}
                    onChange={(event) => {
                      manualFabricEditRef.current = true;
                      setFabricCount(event.target.value.replace(/[^0-9]/g, ""));
                    }}
                    style={{ minHeight: 46 }}
                  />
                </label>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                    gap: 10,
                  }}
                >
                  {[
                    {
                      label: t("import.recap.size"),
                      value: `${previewPattern.width} × ${previewPattern.height}`,
                    },
                    { label: t("import.recap.stitches"), value: String(preview?.filled_count ?? 0) },
                    { label: t("import.recap.colors"), value: String(previewPattern.palette.length) },
                  ].map((tile) => (
                    <div
                      key={tile.label}
                      style={{ padding: "14px 16px", borderRadius: 20, background: "var(--color-surface)" }}
                    >
                      <div
                        className="text-muted"
                        style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em" }}
                      >
                        {tile.label}
                      </div>
                      <div style={{ fontFamily: "var(--font-heading)", fontSize: 20 }}>{tile.value}</div>
                    </div>
                  ))}
                </div>
                <label
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    padding: "14px 16px",
                    borderRadius: 20,
                    background: "var(--color-surface)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={saveAsRecipe}
                    onChange={(event) => setSaveAsRecipe(event.target.checked)}
                    style={{ marginTop: 3, minWidth: 18, minHeight: 18 }}
                  />
                  <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>
                      {t("import.recap.saveRecipe")}
                    </span>
                    <span className="text-muted" style={{ fontSize: 12 }}>
                      {t("import.recap.saveRecipe.hint")}
                    </span>
                  </span>
                </label>
                {saveAsRecipe && (
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span className="text-muted" style={{ fontSize: 12 }}>
                      {t("import.recap.saveRecipe.label")}
                    </span>
                    <input
                      className="input"
                      value={recipeLabel}
                      onChange={(event) => setRecipeLabel(event.target.value)}
                      style={{ minHeight: 46 }}
                    />
                  </label>
                )}
                {recipeError !== null && (
                  <p className="tag tag-accent" style={{ margin: 0 }}>
                    {t("import.recap.saveRecipe.error", { message: recipeError })}
                  </p>
                )}
                {commitError !== null && (
                  <p className="tag tag-accent" style={{ margin: 0 }}>
                    {t("import.finish.error", { message: commitError })}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {step > 1 && (
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ flex: 1, minHeight: 52 }}
              onClick={() => setStep((current) => Math.max(1, current - 1))}
            >
              {t("import.back")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              style={{ flex: 2, minHeight: 52 }}
              disabled={
                (step === 2 && !dimensionsValid) ||
                (step === 3 && palette.length === 0) ||
                (step === 4 &&
                  (previewPattern === null ||
                    name.trim() === "" ||
                    committing ||
                    (saveAsRecipe && recipeLabel.trim() === "")))
              }
              onClick={() => {
                if (step === 2) void goToPalette();
                else if (step === 3) void goToRecap();
                else if (step === STEP_COUNT) void finish();
                else setStep((current) => current + 1);
              }}
            >
              {step === STEP_COUNT ? t("import.finish") : t("import.continue")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
