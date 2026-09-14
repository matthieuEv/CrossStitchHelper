import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Suit une media query.
 *
 * Les maquettes distinguaient iPhone et iPad par une propriété ; dans
 * l'application réelle c'est une question de largeur disponible, pas
 * d'appareil : un iPad en Split View mérite la disposition compacte.
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

/** Seuil de la disposition large : barre latérale et panneau des couleurs. */
export const WIDE_LAYOUT_QUERY = "(min-width: 768px)";

export function useWideLayout(): boolean {
  return useMediaQuery(WIDE_LAYOUT_QUERY);
}

/**
 * Observe la taille d'un élément.
 *
 * Le canvas doit être redessiné quand sa boîte change — rotation de l'appareil,
 * ouverture du panneau des couleurs, clavier logiciel. `resize` sur `window` ne
 * couvre pas ces cas.
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
