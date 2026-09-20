import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { LANGUAGES, useI18n, type Language } from "../i18n";
import {
  backupExportUrl,
  deleteRecipe,
  fetchAutoBackupSetting,
  listRecipes,
  restoreBackup,
  setAutoBackupSetting,
  translateApiError,
  type ApiRecipe,
} from "../lib/api";
import { clearOfflineCache } from "../lib/db";
import { useTheme, type ThemeChoice } from "../lib/theme";
import { useWakeLock } from "../lib/wakeLock";

/** Un document de sauvegarde vide : réutilise exactement le mécanisme de
 * restauration (`app/backup.py::restore_backup`, remplacement complet) pour
 * « effacer toutes les données », plutôt que dupliquer une logique de
 * suppression séparée côté serveur pour le même résultat. */
const EMPTY_BACKUP_DOCUMENT = JSON.stringify({
  format: "csh-backup",
  format_version: 1,
  generated_at: new Date(0).toISOString(),
  patterns: [],
  recipes: [],
});

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

  // Réglage encore local : deviendra une préférence serveur quand un besoin
  // réel de la faire influencer l'extraction/l'import se présentera.
  const [brand, setBrand] = useState<(typeof BRANDS)[number]>("DMC");

  // Sauvegarde automatique quotidienne (Lot 8) : un réglage serveur
  // (`AppMeta`, `app/auto_backup.py`), pas une préférence locale au
  // navigateur — elle doit s'appliquer même si personne n'ouvre
  // l'application ce jour-là.
  const [autoBackup, setAutoBackupState] = useState(true);
  const [autoBackupError, setAutoBackupError] = useState(false);
  const [dataBusy, setDataBusy] = useState(false);
  const [dataMessage, setDataMessage] = useState<string | null>(null);
  const restoreInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchAutoBackupSetting(controller.signal)
      .then((setting) => setAutoBackupState(setting.enabled))
      .catch((error: unknown) => {
        // Un `AbortError` vient de notre propre nettoyage (démontage, ou
        // double montage de StrictMode en développement) — jamais un vrai
        // échec réseau, donc jamais affiché comme tel (même garde que
        // `useServerHealth` ci-dessous).
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAutoBackupError(true);
      });
    return () => controller.abort();
  }, []);

  const toggleAutoBackup = (value: boolean): void => {
    setAutoBackupState(value); // optimiste : reflète le tap immédiatement.
    setAutoBackupError(false);
    void setAutoBackupSetting(value).catch(() => {
      setAutoBackupState(!value); // repli si le serveur est injoignable.
      setAutoBackupError(true);
    });
  };

  const reloadAfterDataChange = (): void => {
    void clearOfflineCache().finally(() => window.location.reload());
  };

  const pickRestoreFile = (): void => restoreInputRef.current?.click();

  const handleRestoreFile = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    event.target.value = ""; // permet de rechoisir le même fichier ensuite.
    if (!file) return;
    if (!window.confirm(t("settings.data.restore.confirm"))) return;

    setDataBusy(true);
    setDataMessage(null);
    void file
      .text()
      .then((text) => {
        JSON.parse(text); // validation locale : message clair avant l'aller-retour réseau.
        return restoreBackup(text);
      })
      .then((summary) => {
        setDataMessage(
          t("settings.data.restore.success", {
            patterns: summary.patterns_count,
            recipes: summary.recipes_count,
          }),
        );
        reloadAfterDataChange();
      })
      .catch((error: unknown) => {
        const message =
          error instanceof SyntaxError
            ? t("settings.data.restore.invalidFile")
            : translateApiError(t, error);
        setDataMessage(t("settings.data.restore.error", { message }));
        setDataBusy(false);
      });
  };

  const eraseAllData = (): void => {
    if (!window.confirm(t("settings.data.erase.confirm"))) return;

    setDataBusy(true);
    setDataMessage(null);
    void restoreBackup(EMPTY_BACKUP_DOCUMENT)
      .then(() => {
        setDataMessage(t("settings.data.erase.done"));
        reloadAfterDataChange();
      })
      .catch((error: unknown) => {
        setDataMessage(t("settings.data.restore.error", { message: translateApiError(t, error) }));
        setDataBusy(false);
      });
  };

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
            <a
              className="btn btn-secondary"
              style={{ minHeight: 48, padding: "0 18px" }}
              href={backupExportUrl()}
            >
              {t("settings.data.export")}
            </a>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ minHeight: 48, padding: "0 18px" }}
              disabled={dataBusy}
              onClick={pickRestoreFile}
            >
              {t("settings.data.restore")}
            </button>
            <input
              ref={restoreInputRef}
              type="file"
              accept="application/json"
              hidden
              onChange={handleRestoreFile}
            />
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
              onChange={toggleAutoBackup}
              label={t("settings.data.autoBackup")}
            />
          </div>
          {autoBackupError && (
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("settings.data.autoBackup.error")}
            </div>
          )}
          {dataMessage && (
            <div className="text-muted" style={{ fontSize: 13 }}>
              {dataMessage}
            </div>
          )}
          <button
            type="button"
            className="btn btn-ghost"
            style={{ alignSelf: "flex-start", minHeight: 44, color: "var(--color-accent-700)" }}
            disabled={dataBusy}
            onClick={eraseAllData}
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
