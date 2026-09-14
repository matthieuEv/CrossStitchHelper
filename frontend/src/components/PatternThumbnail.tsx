import { useEffect, useRef } from "react";

import { useTheme } from "../lib/theme";
import { drawThumbnail, readGridTheme } from "../pattern/render";
import type { Pattern, Progress } from "../pattern/types";

interface PatternThumbnailProps {
  pattern: Pattern;
  progress: Progress | null;
  /** Étiquette lue par les lecteurs d'écran à la place de l'image. */
  label: string;
}

/**
 * Aperçu du motif entier.
 *
 * Redessiné quand le thème change (les cases faites sont délavées vers la
 * couleur de fond) et quand la boîte change de taille.
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

    // Au premier rendu la boîte peut encore être à zéro : on laisse le
    // ResizeObserver déclencher le dessin dès qu'elle est mesurée.
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
