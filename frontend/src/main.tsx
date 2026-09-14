import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { I18nProvider } from "./i18n";
import "./index.css";
import { ThemeProvider } from "./lib/theme";

const container = document.getElementById("root");
if (container === null) throw new Error("Élément racine introuvable");

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <App />
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
);
