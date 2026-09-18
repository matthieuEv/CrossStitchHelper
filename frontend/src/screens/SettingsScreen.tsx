import { useEffect, useState } from "react";

import { LANGUAGES, useI18n, type Language } from "../i18n";
import { deleteRecipe, listRecipes, type ApiRecipe } from "../lib/api";
import { useTheme, type ThemeChoice } from "../lib/theme";
import { useWakeLock } from "../lib/wakeLock";

const BRANDS = ["DMC", "Anchor", "Madeira"] as const;
const LANGUAGE_LABELS: Record<Language, string> = { fr: "Français", en: "English" };

interface SettingsScreenProps {
  version: string;
}

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  );
}

export function SettingsScreen({ version }: SettingsScreenProps) {
  const { t, language, setLanguage } = useI18n();
  const { choice, setChoice } = useTheme();
  const wakeLock = useWakeLock();

  // Réglages encore locaux : ils deviendront des préférences serveur quand
  // l'API de configuration existera (Lot 3).
  const [brand, setBrand] = useState<(typeof BRANDS)[number]>("DMC");
  const [autoBackup, setAutoBackup] = useState(true);

  const [recipes, setRecipes] = useState<ApiRecipe[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    void listRecipes(controller.signal)
      .then(setRecipes)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const removeRecipe = (recipeId: string): void => {
    setRecipes((current) => current.filter((recipe) => recipe.id !== recipeId));
    void deleteRecipe(recipeId).catch(() => undefined);
  };

  const themeChoices: Array<{ value: ThemeChoice; label: string }> = [
    { value: "light", label: t("settings.theme.light") },
    { value: "dark", label: t("settings.theme.dark") },
    { value: "system", label: t("settings.theme.system") },
  ];

  return (
    <div className="screen">
      <h2 style={{ margin: "0 0 18px" }}>{t("settings.title")}</h2>

      <div style={{ maxWidth: 620, display: "flex", flexDirection: "column", gap: 14 }}>
        <section className="panel">
          <div>
            <div className="panel-title">{t("settings.brand")}</div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("settings.brand.hint")}
            </div>
          </div>
          <div className="seg" style={{ alignSelf: "flex-start" }}>
            {BRANDS.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={brand === item}
                onClick={() => setBrand(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div>
            <div className="panel-title">{t("settings.theme")}</div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("settings.theme.hint")}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {themeChoices.map((item) => (
              <button
                key={item.value}
                type="button"
                className={choice === item.value ? "btn btn-primary" : "btn btn-secondary"}
                style={{ minHeight: 44, padding: "0 18px", fontSize: 14 }}
                aria-pressed={choice === item.value}
                onClick={() => setChoice(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {wakeLock.supported && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                minHeight: 48,
                fontSize: 14,
              }}
            >
              <span>{t("settings.keepAwake")}</span>
              <Switch
                checked={wakeLock.enabled}
                onChange={wakeLock.setEnabled}
                label={t("settings.keepAwake")}
              />
            </div>
          )}
        </section>

        <section className="panel">
          <div>
            <div className="panel-title">{t("settings.language")}</div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("settings.language.hint")}
            </div>
          </div>
          <div className="seg" style={{ alignSelf: "flex-start" }}>
            {LANGUAGES.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={language === item}
                onClick={() => setLanguage(item)}
              >
                {LANGUAGE_LABELS[item]}
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div>
            <div className="panel-title">{t("settings.data")}</div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn btn-secondary" style={{ minHeight: 48, padding: "0 18px" }}>
              {t("settings.data.export")}
            </button>
            <button type="button" className="btn btn-secondary" style={{ minHeight: 48, padding: "0 18px" }}>
              {t("settings.data.restore")}
            </button>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              minHeight: 48,
              fontSize: 14,
            }}
          >
            <span>{t("settings.data.autoBackup")}</span>
            <Switch
              checked={autoBackup}
              onChange={setAutoBackup}
              label={t("settings.data.autoBackup")}
            />
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ alignSelf: "flex-start", minHeight: 44, color: "var(--color-accent-700)" }}
          >
            {t("settings.data.erase")}
          </button>
        </section>

        <section className="panel">
          <div>
            <div className="panel-title">{t("settings.recipes")}</div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("settings.recipes.hint")}
            </div>
          </div>
          {recipes.length === 0 ? (
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("settings.recipes.empty")}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recipes.map((recipe) => (
                <div
                  key={recipe.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    padding: "10px 14px",
                    borderRadius: 16,
                    background: "var(--color-surface)",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 14 }}>{recipe.label}</span>
                    <span className="text-muted" style={{ fontSize: 11 }}>
                      {t("settings.recipes.usage", { count: recipe.usage_count })}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ minHeight: 40, color: "var(--color-accent-700)" }}
                    onClick={() => removeRecipe(recipe.id)}
                  >
                    {t("settings.recipes.delete")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <div
          className="text-muted"
          style={{
            padding: 18,
            borderRadius: 24,
            border: "1px solid var(--color-divider)",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          {t("settings.about", { version })}
        </div>
      </div>
    </div>
  );
}
