import { useEffect, useRef } from "react";

import { useTheme } from "../lib/theme";
import { drawThumbnail, readGridTheme } from "../pattern/render";
import type { Pattern, Progress } from "../pattern/types";

interface PatternThumbnailProps {
  pattern: Pattern;
  progress: Progress | null;
  /** Label read by screen readers in place of the image. */
  label: string;
}

/**
 * Preview of the whole pattern.
 *
 * Redrawn when the theme changes (done cells are washed out towards the
 * background colour) and when the box changes size.
 */
export function PatternThumbnail({ pattern, progress, label }: PatternThumbnailProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { resolved } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) return;

    const render = (): void => {
      drawThumbnail(canvas, pattern, progress, readGridTheme(canvas));
    };

    // On first render the box can still be zero-sized: let the
    // ResizeObserver trigger the drawing as soon as it is measured.
    render();
    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [pattern, progress, resolved]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={label}
      style={{ width: "100%", height: "100%", display: "block" }}
    />
  );
}
