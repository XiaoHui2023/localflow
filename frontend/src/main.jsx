import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { TooltipProvider } from "./Tooltip.jsx";
import "./index.css";
import "./extra.css";
import "./round6.css";
import "./round7.css";
import "./case-picker.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <TooltipProvider><App /></TooltipProvider>
  </React.StrictMode>,
);
