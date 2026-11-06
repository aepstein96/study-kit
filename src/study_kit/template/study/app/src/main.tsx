import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Shared base theme; study-specific rules go in ./style.css, which cascades after it.
import "study-kit/study-theme/theme.css";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
