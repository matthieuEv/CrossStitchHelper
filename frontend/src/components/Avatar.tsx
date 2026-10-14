import type { CSSProperties } from "react";

interface AvatarProps {
  initials: string;
  /** 0-359, from the server (`ProfileCard.avatar_hue`): stable per profile. */
  hue: number;
  size?: "sm" | "md" | "lg";
}

/** A profile's round badge: initials on a colour of its own (Lot 10). The
 * hue is the profile's; saturation and lightness come from the theme
 * (`--avatar-*`, `index.css`), so it reads well in light and dark mode. */
export function Avatar({ initials, hue, size = "md" }: AvatarProps) {
  const className = size === "md" ? "avatar" : `avatar avatar-${size}`;
  return (
    <span className={className} style={{ "--avatar-hue": hue } as CSSProperties} aria-hidden="true">
      {initials}
    </span>
  );
}
