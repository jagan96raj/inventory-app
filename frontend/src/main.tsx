import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import IdleSessionGuard from "./components/IdleSessionGuard";
import { ThemeProvider } from "./lib/theme";
import { DensityProvider } from "./lib/density";
import Toaster from "./components/ui/Toaster";
import { installPreventNumberInputWheel } from "./lib/preventNumberInputWheel";
import "./index.css";
import "./styles/index.css";

installPreventNumberInputWheel();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <DensityProvider>
        <BrowserRouter>
          <AuthProvider>
            <IdleSessionGuard />
            <App />
            <Toaster />
          </AuthProvider>
        </BrowserRouter>
      </DensityProvider>
    </ThemeProvider>
  </React.StrictMode>
);
