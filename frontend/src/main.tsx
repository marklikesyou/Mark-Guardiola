import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/barlow-semi-condensed/latin-400.css";
import "@fontsource/barlow-semi-condensed/latin-500.css";
import "@fontsource/barlow-semi-condensed/latin-600.css";
import "@fontsource/barlow-semi-condensed/latin-700.css";
import "@fontsource/barlow-semi-condensed/latin-800.css";
import "@fontsource/yellowtail/latin-400.css";
import "./styles/tokens.css";
import "./styles/app.css";
import App from "./App";

const container = document.getElementById("root");
if (container === null) {
  throw new Error();
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
