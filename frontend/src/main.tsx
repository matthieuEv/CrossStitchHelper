import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { AuthGate } from "./AuthGate";
import { I18nProvider } from "./i18n";
import "./index.css";
import { ThemeProvider } from "./lib/theme";
import { AuthProvider } from "./state/auth";

const container = document.getElementById("root");
if (container === null) throw new Error("Root element not found");

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <AuthProvider>
          <AuthGate />
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
);
