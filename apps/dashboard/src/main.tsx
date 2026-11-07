import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts are bundled (latin subsets) so Knack works with wifi off. Weights are 400 and 600 only (docs/KNACK_UX.md section 6).
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/source-sans-3/latin-400.css";
import "@fontsource/source-sans-3/latin-600.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "../../../packages/design/tokens.css";
import "../../../packages/design/components.css";
import "./styles/app.css";
import { App } from "./App";
import { initTheme } from "./components/shell/theme";

// The desktop app serves this page from its own scheme (app://knack); there the sidebar leaves 40 px for the traffic lights.
if (window.location.protocol === "app:") document.documentElement.dataset.shell = "desktop";
initTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
