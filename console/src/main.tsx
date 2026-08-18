import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ApiProvider } from "./hooks/useApi";
import "./styles/base.css";

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <ApiProvider>
      <App />
    </ApiProvider>
  </StrictMode>,
);
