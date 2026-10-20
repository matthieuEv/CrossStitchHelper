import { useEffect, useId, useRef, useState } from "react";
import type { ApiThreadShade } from "../lib/api";

interface DmcCodeInputProps {
  value: string;
  /** The chart, in printed-chart order; empty when it could not be loaded. */
  shades: readonly ApiThreadShade[];
  placeholder: string;
  label: string;
  onChange: (code: string) => void;
  onFocus: () => void;
  onBlur: () => void;
  /** A suggestion was picked: the field keeps the focus. */
  onPick: (shade: ApiThreadShade) => void;
}

const LIST_MAX_HEIGHT = 264;
/** Below this much room under the field, the list opens above it if there is more room there. */
const LIST_MIN_HEIGHT = 160;

interface ListLayout {
  maxWidth: number;
  maxHeight: number;
  above: boolean;
}

/**
 * Where the list fits, from the area actually visible (`visualViewport`, which
 * excludes the on-screen keyboard): never past the screen's right edge on a
 * phone, and above the field when the keyboard leaves too little room below.
 */
function measureLayout(input: HTMLElement): ListLayout {
  const rect = input.getBoundingClientRect();
  const viewport = window.visualViewport;
  const top = viewport?.offsetTop ?? 0;
  const bottom = top + (viewport?.height ?? window.innerHeight);
  const right =
    (viewport?.offsetLeft ?? 0) + (viewport?.width ?? window.innerWidth);
  const below = bottom - rect.bottom - 12;
  const above = rect.top - top - 12;
  const openAbove = below < LIST_MIN_HEIGHT && above > below;
  return {
    maxWidth: Math.max(rect.width, right - rect.left - 12),
    maxHeight: Math.max(
      88,
      Math.min(LIST_MAX_HEIGHT, openAbove ? above : below),
    ),
    above: openAbove,
  };
}

/**
 * Code field with the DMC chart's suggestions in a list of the app's own
 * (issue #39). A native `<datalist>` only shows up as a drop-down with a
 * hardware keyboard: with the on-screen keyboard, iPadOS and iOS Safari move
 * its suggestions into the keyboard's shortcut bar, where they go unnoticed.
 */
export function DmcCodeInput({
  value,
  shades,
  placeholder,
  label,
  onChange,
  onFocus,
  onBlur,
  onPick,
}: DmcCodeInputProps) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const [layout, setLayout] = useState<ListLayout | null>(null);

  const query = value.trim().toLowerCase();
  const matches =
    query === ""
      ? shades
      : [
          ...shades.filter((shade) =>
            shade.code.toLowerCase().startsWith(query),
          ),
          ...shades.filter(
            (shade) =>
              !shade.code.toLowerCase().startsWith(query) &&
              shade.name.toLowerCase().includes(query),
          ),
        ];
  const expanded = open && matches.length > 0;

  const openList = (): void => {
    if (inputRef.current !== null) setLayout(measureLayout(inputRef.current));
    setOpen(true);
  };

  // The on-screen keyboard slides up after the focus, shrinking the visible
  // area, and Safari then scrolls the field into view: measured again
  // whenever either happens while the list is open.
  useEffect(() => {
    if (!open) return;
    const viewport = window.visualViewport;
    const remeasure = (): void => {
      if (inputRef.current !== null) setLayout(measureLayout(inputRef.current));
    };
    viewport?.addEventListener("resize", remeasure);
    viewport?.addEventListener("scroll", remeasure);
    window.addEventListener("resize", remeasure);
    // Capture: catches the scrolling of any container holding the field.
    window.addEventListener("scroll", remeasure, true);
    return () => {
      viewport?.removeEventListener("resize", remeasure);
      viewport?.removeEventListener("scroll", remeasure);
      window.removeEventListener("resize", remeasure);
      window.removeEventListener("scroll", remeasure, true);
    };
  }, [open]);

  const pick = (shade: ApiThreadShade): void => {
    setOpen(false);
    setHighlighted(-1);
    onPick(shade);
  };

  return (
    <div style={{ position: "relative", flex: "none" }}>
      <input
        ref={inputRef}
        className="input"
        style={{ width: 90 }}
        placeholder={placeholder}
        aria-label={label}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={
          expanded && highlighted >= 0 ? `${listId}-${highlighted}` : undefined
        }
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        spellCheck={false}
        value={value}
        onFocus={() => {
          onFocus();
          openList();
        }}
        // A tap on a field that kept the focus (after a pick) reopens it.
        onClick={() => {
          if (!open) openList();
        }}
        onChange={(event) => {
          onChange(event.target.value);
          setHighlighted(-1);
          if (!open) openList();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
          } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) openList();
            const step = event.key === "ArrowDown" ? 1 : -1;
            setHighlighted((current) =>
              Math.min(matches.length - 1, Math.max(0, current + step)),
            );
          } else if (
            event.key === "Enter" &&
            expanded &&
            matches[highlighted] !== undefined
          ) {
            event.preventDefault();
            pick(matches[highlighted]);
          }
        }}
        onBlur={() => {
          setOpen(false);
          setHighlighted(-1);
          onBlur();
        }}
      />
      {expanded && (
        <div
          id={listId}
          role="listbox"
          aria-label={label}
          className="menu elev-md"
          style={{
            left: 0,
            right: "auto",
            minWidth: 0,
            width: "max-content",
            maxWidth: layout?.maxWidth,
            maxHeight: layout?.maxHeight ?? LIST_MAX_HEIGHT,
            ...(layout?.above === true
              ? { top: "auto", bottom: "calc(100% + 6px)" }
              : {}),
            overflowY: "auto",
            flexWrap: "nowrap",
          }}
          // Keeps the focus in the field: without it, the blur would close the
          // list before a tap on an option is seen.
          onPointerDown={(event) => event.preventDefault()}
          onMouseDown={(event) => event.preventDefault()}
        >
          {matches.map((shade, index) => (
            <div
              key={shade.code}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === highlighted}
              className="menu-item"
              style={{
                flex: "none",
                background:
                  index === highlighted
                    ? "color-mix(in srgb, var(--color-text) 7%, transparent)"
                    : undefined,
              }}
              onClick={() => pick(shade)}
            >
              <span
                aria-hidden
                style={{
                  flex: "none",
                  width: 18,
                  height: 18,
                  borderRadius: 6,
                  background: shade.rgb_hex,
                  boxShadow: "inset 0 0 0 1px rgba(0, 0, 0, 0.18)",
                }}
              />
              <span style={{ fontWeight: 600, flex: "none" }}>
                {shade.code}
              </span>
              <span
                className="text-muted"
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {shade.name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
