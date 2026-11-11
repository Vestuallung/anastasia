import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { StudioRoot } from "./components/StudioHome-11月7日";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StudioRoot />
  </StrictMode>,
);

