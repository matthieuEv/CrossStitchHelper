import { useEffect, useRef, useState } from "react";

import { useT } from "../i18n";
import { useAuth, useCurrentUser } from "../state/auth";
import { Avatar } from "./Avatar";

interface ProfileMenuProps {
  /** Opens Settings, where "My account" is. */
  onOpenAccount: () => void;
  /** Open the menu upwards (bottom of the sidebar) rather than downwards. */
  up?: boolean;
  /** Avatar only, without the first name — a phone's Library header has no
   * room for both next to the title and "Sort". */
  compact?: boolean;
}

/**
 * "Switch profile" (Lot 10): sends this profile's queued progress first and,
 * if some cannot leave (no network), says so before handing the device over
 * — they are kept for this profile's next login, never lost.
 */
export function useSwitchProfile(): { busy: boolean; switchNow: () => Promise<void> } {
  const t = useT();
  const { flushQueued, switchProfile } = useAuth();
  const [busy, setBusy] = useState(false);

  const switchNow = async (): Promise<void> => {
    setBusy(true);
    const left = await flushQueued();
    if (left > 0 && !window.confirm(t("profile.switch.pending", { count: left }))) {
      setBusy(false);
      return;
    }
    await switchProfile();
  };

  return { busy, switchNow };
}

/**
 * The logged-in profile's chip (Lot 10): who is stitching, and the way to
 * hand the device to someone else ("Switch profile").
 */
export function ProfileMenu({ onOpenAccount, up = false, compact = false }: ProfileMenuProps) {
  const t = useT();
  const user = useCurrentUser();
  const { busy, switchNow } = useSwitchProfile();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        className={compact ? "profile-chip is-compact" : "profile-chip"}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("profile.menu", { name: user.first_name })}
        onClick={() => setOpen((value) => !value)}
      >
        <Avatar initials={user.initials} hue={user.avatar_hue} size="sm" />
        {!compact && user.first_name}
      </button>
      {open && (
        <div
          role="menu"
          aria-label={t("profile.menu", { name: user.first_name })}
          className="menu elev-md"
          style={up ? { top: "auto", bottom: "calc(100% + 6px)", left: 0, right: "auto" } : undefined}
        >
          <div className="text-muted" style={{ padding: "6px 12px 8px", fontSize: 13 }}>
            {user.first_name} {user.last_name}
            {user.role === "admin" && ` · ${t("account.role.admin")}`}
          </div>
          <button
            type="button"
            role="menuitem"
            className="menu-item"
            onClick={() => {
              setOpen(false);
              onOpenAccount();
            }}
          >
            {t("profile.account")}
          </button>
          <button
            type="button"
            role="menuitem"
            className="menu-item"
            disabled={busy}
            onClick={() => void switchNow()}
          >
            {t("profile.switch")}
          </button>
        </div>
      )}
    </div>
  );
}
