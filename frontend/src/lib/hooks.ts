import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Tracks a media query.
 *
 * The mockups distinguished iPhone and iPad by a prop; in the real
 * application it is a matter of available width, not of device: an iPad in
 * Split View deserves the compact layout.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => window.matchMedia(query).matches);

  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const onChange = (event: MediaQueryListEvent): void => setMatches(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Wide layout threshold: sidebar and colour panel. */
export const WIDE_LAYOUT_QUERY = "(min-width: 768px)";

export function useWideLayout(): boolean {
  return useMediaQuery(WIDE_LAYOUT_QUERY);
}

/**
 * Observes an element's size.
 *
 * The canvas must be redrawn when its box changes — device rotation, opening
 * the colour panel, on-screen keyboard. `resize` on `window` does not cover
 * these cases.
 */
export function useElementSize<T extends HTMLElement>(): [
  React.RefObject<T | null>,
  { width: number; height: number },
] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const element = ref.current;
    if (element === null) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry === undefined) return;
      const box = entry.contentRect;
      setSize({ width: Math.round(box.width), height: Math.round(box.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, size];
}
