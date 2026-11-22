import { useEffect, useRef, useState, type RefObject } from 'react';

/** The content width of a box once laid out (ResizeObserver), the fallback
 *  until then. A chart drawn at this width never overflows its card. */
export function useBoxWidth<T extends HTMLElement>(fallback: number): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [measured, setMeasured] = useState<number | null>(null);

  useEffect(() => {
    const box = ref.current;
    if (!box || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setMeasured(width > 0 ? Math.round(width) : null);
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  return [ref, measured ?? fallback];
}

/** True while the media query matches; false where matchMedia is missing. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false));
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return undefined;
    }
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    setMatches(list.matches);
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}
