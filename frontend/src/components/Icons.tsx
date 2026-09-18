/** Icônes de l'interface, reprises des maquettes. Trait épais, bouts arrondis. */

interface IconProps {
  size?: number;
}

function Svg({ size = 22, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.75"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

export function MinusIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14" />
    </Svg>
  );
}

export function GridIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </Svg>
  );
}

export function TrackIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
    </Svg>
  );
}

export function StatsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 20V11M12 20V4M19 20v-6" />
    </Svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h10M18 7h2M4 17h5M13 17h7" />
      <circle cx="16" cy="7" r="2.4" />
      <circle cx="11" cy="17" r="2.4" />
    </Svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 6l-6 6 6 6" />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function UndoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 8h10a5 5 0 1 1 0 10H7" />
      <path d="M7.5 4.5L4 8l3.5 3.5" />
    </Svg>
  );
}

export function StitchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 5l14 14M19 5L5 19" />
    </Svg>
  );
}

export function PanIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3v18M3 12h18" />
      <path d="M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3" />
    </Svg>
  );
}

export function SelectIcon(props: IconProps) {
  return (
    <svg
      width={props.size ?? 22}
      height={props.size ?? 22}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.75"
      strokeLinecap="round"
      strokeDasharray="4 3"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="4" y="4" width="16" height="16" rx="3" />
    </svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 16V4M8 8l4-4 4 4" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Svg>
  );
}

/** Point 1/2 (Lot 8) : triangle occupant la moitié de la case, diagonale —
 * même convention que le rendu canvas (`pattern/render.ts`). */
export function HalfStitchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 4l16 16" />
    </Svg>
  );
}

/** Point 1/4 (Lot 8) : un triangle plus petit qu'un point 1/2, même coin. */
export function QuarterStitchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 4l7 7M4 4v7M4 4h7" />
    </Svg>
  );
}

/** Point arrière (Lot 8) : trait le long des coins de case. */
export function BackstitchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 17L8 8l4 5 4-8 4 7" />
    </Svg>
  );
}

/** Nœud (Lot 8) : point rond au centre de case. */
export function FrenchKnotIcon(props: IconProps) {
  return (
    <svg
      width={props.size ?? 22}
      height={props.size ?? 22}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.75"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Œil barré : masque les cases déjà brodées pour ne montrer que le reste à faire. */
export function EyeOffIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 3l18 18" />
      <path d="M10.6 5.2A10.4 10.4 0 0 1 12 5c5 0 9 4 10 7-.4 1.1-1.2 2.4-2.3 3.5M6.3 6.3C4.2 7.7 2.7 9.6 2 12c1 3 5 7 10 7 1.4 0 2.7-.3 3.9-.8" />
      <path d="M9.5 10a3.4 3.4 0 0 0 4.5 4.5" />
    </Svg>
  );
}
