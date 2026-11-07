import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts are bundled (latin subsets) so the demo works with wifi off.
import "@fontsource/bricolage-grotesque/latin-500.css";
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/bricolage-grotesque/latin-700.css";
import "@fontsource/source-sans-3/latin-400.css";
import "@fontsource/source-sans-3/latin-500.css";
import "@fontsource/source-sans-3/latin-600.css";
import "@fontsource/source-sans-3/latin-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/jetbrains-mono/latin-700.css";
import "../../../packages/design/tokens.css";
import "../../../packages/design/components.css";
import "./styles/app.css";
import "./styles/shell.css";
import { App } from "./App";

// Inside the Knack desktop app (apps/desktop, src/preload/knack.ts) on a Mac, the window has a hidden-inset title bar: the traffic lights sit on top of the
// sidebar, so styles/shell.css leaves room under them and lets the top edge drag the window. In a browser tab there is no knackShell and nothing changes.
const shell = (window as unknown as { knackShell?: { platform?: string } }).knackShell;
if (shell?.platform === "darwin") document.documentElement.dataset.knackShell = "mac-inset";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
