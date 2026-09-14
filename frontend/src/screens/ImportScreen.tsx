import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { CameraIcon, UploadIcon } from "../components/Icons";
import { PatternThumbnail } from "../components/PatternThumbnail";
import { useT } from "../i18n";
import { useNumberFormat } from "../lib/format";
import { countByColor, summarise } from "../pattern/counts";
import type { Pattern } from "../pattern/types";

type Edge = "left" | "top" | "right" | "bottom";
interface Crop {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const STEP_COUNT = 4;
/** Marge maximale qu'une poignée peut prendre, pour garder un cadre utilisable. */
const MAX_INSET = 42;

interface ImportScreenProps {
  /** Motif servant d'aperçu tant que l'extraction réelle n'existe pas. */
  preview: Pattern;
  wide: boolean;
  onCancel: () => void;
  onFinish: () => void;
}

export function ImportScreen({ preview, wide, onCancel, onFinish }: ImportScreenProps) {
  const t = useT();
  const formatNumber = useNumberFormat();

  const [step, setStep] = useState(1);
  const [crop, setCrop] = useState<Crop>({ left: 9, top: 8, right: 8, bottom: 11 });
  const [legend, setLegend] = useState(() =>
    preview.palette.map((entry, index) => ({
      ...entry,
      // Deux entrées marquées douteuses : la maquette montrait ce que
      // l'assistant doit faire quand le moteur n'est pas sûr de sa lecture.
      uncertain: index === 4 || index === 11,
    })),
  );

  const stageRef = useRef<HTMLDivElement>(null);
  const dragEdgeRef = useRef<Edge | null>(null);

  const stepLabels = [
    t("import.step.file"),
    t("import.step.crop"),
    t("import.step.legend"),
    t("import.step.recap"),
  ];

  const startDrag = (edge: Edge) => (event: ReactPointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    dragEdgeRef.current = edge;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const edge = dragEdgeRef.current;
    const stage = stageRef.current;
    if (edge === null || stage === null) return;

    const box = stage.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 100;
    const y = ((event.clientY - box.top) / box.height) * 100;
    const clamp = (value: number): number => Math.max(0, Math.min(MAX_INSET, value));

    setCrop((current) => {
      switch (edge) {
        case "left":
          return { ...current, left: clamp(x) };
        case "right":
          return { ...current, right: clamp(100 - x) };
        case "top":
          return { ...current, top: clamp(y) };
        case "bottom":
          return { ...current, bottom: clamp(100 - y) };
      }
    });
  }, []);

  const endDrag = useCallback(() => {
    dragEdgeRef.current = null;
  }, []);

  // Dimensions déduites du cadrage : l'assistant propose, l'utilisateur voit
  // immédiatement l'effet de son geste.
  const detectedColumns = Math.round((preview.width * (100 - crop.left - crop.right)) / 82);
  const detectedRows = Math.round(detectedColumns * (preview.height / preview.width));

  const totals = summarise(countByColor(preview, new Uint8Array(preview.width * preview.height)));
  const uncertainCount = legend.filter((entry) => entry.uncertain).length;

  const centerX = `${crop.left + (100 - crop.left - crop.right) / 2}%`;
  const centerY = `${crop.top + (100 - crop.top - crop.bottom) / 2}%`;

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

        <ol
          style={{
            display: "flex",
            gap: 8,
            listStyle: "none",
            margin: 0,
            padding: 0,
          }}
        >
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
                {t("import.drop.choose")}
                <input
                  type="file"
                  accept="application/pdf,image/png,image/jpeg"
                  style={{ display: "none" }}
                  onChange={() => setStep(2)}
                />
              </label>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              style={{ minHeight: 52, gap: 10 }}
              onClick={() => setStep(2)}
            >
              <CameraIcon size={20} />
              {t("import.photo")}
            </button>
            <p
              className="text-muted"
              style={{
                fontSize: 12,
                lineHeight: 1.6,
                padding: "14px 16px",
                borderRadius: 20,
                background: "var(--color-surface)",
                margin: 0,
              }}
            >
              {t("import.photo.hint")}
            </p>
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("import.crop.hint")}
            </div>

            <div
              ref={stageRef}
              className="crop-stage"
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerLeave={endDrag}
            >
              <PatternThumbnail pattern={preview} progress={null} label={t("import.step.crop")} />
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
              <div
                className="crop-handle"
                onPointerDown={startDrag("top")}
                style={{
                  left: centerX,
                  top: `${crop.top}%`,
                  transform: "translate(-50%, -50%)",
                  width: 64,
                  height: 44,
                  cursor: "ns-resize",
                }}
              >
                <span style={{ width: 52, height: 8 }} />
              </div>
              <div
                className="crop-handle"
                onPointerDown={startDrag("bottom")}
                style={{
                  left: centerX,
                  bottom: `${crop.bottom}%`,
                  transform: "translate(-50%, 50%)",
                  width: 64,
                  height: 44,
                  cursor: "ns-resize",
                }}
              >
                <span style={{ width: 52, height: 8 }} />
              </div>
              <div
                className="crop-handle"
                onPointerDown={startDrag("left")}
                style={{
                  top: centerY,
                  left: `${crop.left}%`,
                  transform: "translate(-50%, -50%)",
                  width: 44,
                  height: 64,
                  cursor: "ew-resize",
                }}
              >
                <span style={{ width: 8, height: 52 }} />
              </div>
              <div
                className="crop-handle"
                onPointerDown={startDrag("right")}
                style={{
                  top: centerY,
                  right: `${crop.right}%`,
                  transform: "translate(50%, -50%)",
                  width: 44,
                  height: 64,
                  cursor: "ew-resize",
                }}
              >
                <span style={{ width: 8, height: 52 }} />
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="tag tag-neutral" style={{ minHeight: 32 }}>
                {t("import.crop.detected", { cols: detectedColumns, rows: detectedRows })}
              </span>
              <button type="button" className="btn btn-ghost" style={{ minHeight: 44 }}>
                {t("import.crop.redetect")}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div className="text-muted" style={{ fontSize: 13 }}>
                {t("import.legend.hint", { count: legend.length })}
              </div>
              <span className="tag tag-accent-2" style={{ minHeight: 32 }}>
                {t("import.legend.confidence", {
                  sure: legend.length - uncertainCount,
                  unsure: uncertainCount,
                })}
              </span>
            </div>

            {wide ? (
              <div
                style={{
                  borderRadius: 22,
                  background: "var(--color-surface)",
                  padding: "6px 12px 10px",
                  maxHeight: 420,
                  overflow: "auto",
                }}
              >
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 48 }}>{t("import.legend.symbol")}</th>
                      <th style={{ width: 64 }}>{t("import.legend.color")}</th>
                      <th>{t("import.legend.code")}</th>
                      <th>{t("import.legend.name")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {legend.map((entry, index) => (
                      <tr key={entry.code}>
                        <td style={{ fontSize: 17, textAlign: "center" }}>{entry.symbol}</td>
                        <td>
                          <div className="swatch" style={{ width: 34, height: 34, background: entry.hex }} />
                        </td>
                        <td>
                          <input
                            className="input"
                            style={{ width: 96 }}
                            value={entry.code}
                            aria-label={t("import.legend.code")}
                            onChange={(event) =>
                              setLegend((current) =>
                                current.map((item, i) =>
                                  i === index ? { ...item, code: event.target.value } : item,
                                ),
                              )
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="input"
                            style={{ minWidth: 140 }}
                            value={entry.name}
                            aria-label={t("import.legend.name")}
                            onChange={(event) =>
                              setLegend((current) =>
                                current.map((item, i) =>
                                  i === index ? { ...item, name: event.target.value } : item,
                                ),
                              )
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {legend.map((entry, index) => (
                  <div
                    key={entry.code}
                    style={{
                      display: "flex",
                      gap: 12,
                      padding: 12,
                      borderRadius: 20,
                      background: "var(--color-surface)",
                      border: `1px solid ${entry.uncertain ? "var(--color-accent)" : "transparent"}`,
                    }}
                  >
                    <div
                      style={{
                        flex: "none",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: 6,
                        width: 46,
                      }}
                    >
                      <div className="swatch" style={{ width: 46, height: 46, background: entry.hex }} />
                      <div
                        style={{
                          width: 34,
                          height: 26,
                          display: "grid",
                          placeItems: "center",
                          borderRadius: 8,
                          background: "var(--color-bg)",
                          fontSize: 16,
                          lineHeight: 1,
                        }}
                      >
                        {entry.symbol}
                      </div>
                    </div>
                    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className="text-muted" style={{ flex: "none", fontSize: 12, width: 74 }}>
                          {t("import.legend.code")}
                        </span>
                        <input
                          className="input"
                          style={{ flex: 1, minWidth: 0, minHeight: 46 }}
                          value={entry.code}
                          onChange={(event) =>
                            setLegend((current) =>
                              current.map((item, i) =>
                                i === index ? { ...item, code: event.target.value } : item,
                              ),
                            )
                          }
                        />
                      </label>
                      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span className="text-muted" style={{ flex: "none", fontSize: 12, width: 74 }}>
                          {t("import.legend.name")}
                        </span>
                        <input
                          className="input"
                          style={{ flex: 1, minWidth: 0, minHeight: 46 }}
                          value={entry.name}
                          onChange={(event) =>
                            setLegend((current) =>
                              current.map((item, i) =>
                                i === index ? { ...item, name: event.target.value } : item,
                              ),
                            )
                          }
                        />
                      </label>
                      {entry.uncertain && (
                        <span className="tag tag-accent" style={{ alignSelf: "flex-start", minHeight: 28 }}>
                          {t("import.legend.uncertain")}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div
              style={{
                borderRadius: 22,
                overflow: "hidden",
                background: "var(--color-neutral-200)",
                aspectRatio: "1.4",
              }}
            >
              <PatternThumbnail pattern={preview} progress={null} label={preview.name} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <h4 style={{ margin: 0 }}>{preview.name}</h4>
              <div className="text-muted" style={{ fontSize: 13 }}>
                {t("import.recap.source", { pages: 4 })}
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                gap: 10,
              }}
            >
              {[
                { label: t("import.recap.size"), value: `${preview.width} × ${preview.height}` },
                { label: t("import.recap.stitches"), value: formatNumber(totals.total) },
                { label: t("import.recap.colors"), value: `${preview.palette.length} DMC` },
              ].map((tile) => (
                <div key={tile.label} style={{ padding: "14px 16px", borderRadius: 20, background: "var(--color-surface)" }}>
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
              onClick={() => (step === STEP_COUNT ? onFinish() : setStep((current) => current + 1))}
            >
              {step === STEP_COUNT ? t("import.finish") : t("import.continue")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
