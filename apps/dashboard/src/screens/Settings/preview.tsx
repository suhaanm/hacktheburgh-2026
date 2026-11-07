// Dev-only preview of the Settings contents in a plain frame (see settings-preview.html). The shell's sheet is the real host.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/source-sans-3/latin-400.css";
import "@fontsource/source-sans-3/latin-600.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "../../../../../packages/design/tokens.css";
import "../../../../../packages/design/components.css";
import "../../styles/app.css";
import { ToastHost } from "../../components/Toasts";
import { getTheme, applyTheme } from "./prefs";
import Settings from "./Settings";

applyTheme(getTheme());
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastHost>
      <main style={{ maxWidth: 560, margin: "0 auto", padding: "32px 24px 64px" }}>
        <h1 style={{ font: "600 var(--text-xl)/1.25 var(--font-display)", margin: "0 0 16px" }}>Settings</h1>
        <Settings section={window.location.hash.replace(/^#/, "") || undefined} />
      </main>
    </ToastHost>
  </StrictMode>,
);
