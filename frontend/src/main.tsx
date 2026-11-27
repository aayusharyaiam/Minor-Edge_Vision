import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import SplitView from "./pages/SplitView";
import Overview from "./pages/Overview";
import TestMode from "./pages/TestMode";
import Owner from "./pages/Owner";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<SplitView />} />
          <Route path="project" element={<Overview />} />
          <Route path="owner" element={<Owner />} />
        </Route>
        {/* Test Mode is standalone: opened in its own tab, no shared layout. */}
        <Route path="test" element={<Layout standalone />}>
          <Route index element={<TestMode />} />
        </Route>
        <Route path="*" element={<Layout />}>
          <Route path="*" element={<SplitView />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
