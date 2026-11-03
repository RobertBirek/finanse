import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SessionQueryProvider } from "./lib/SessionQueryProvider";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SessionQueryProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </SessionQueryProvider>
  </React.StrictMode>,
);
