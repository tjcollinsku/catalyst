import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layouts/AppShell";
import { ShellContextProvider } from "./contexts/ShellContext";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { useTheme } from "./hooks/useTheme";
import { initCSRF } from "./api";

// Views
import { DashboardView } from "./views/DashboardView";
import { CasesListView } from "./views/CasesListView";
import { CaseDetailView } from "./views/CaseDetailView";
import { EntityBrowserView } from "./views/EntityBrowserView";
import { EntityDetailView } from "./views/EntityDetailView";
import { TriageView } from "./views/TriageView";
import { ReferralsView } from "./views/ReferralsView";
import { SearchView } from "./views/SearchView";
import { SettingsView } from "./views/SettingsView";

// Case detail tabs
import { DocumentsTab } from "./components/cases/DocumentsTab";
import { ReferralsTab } from "./components/cases/ReferralsTab";
import { FinancialsTab } from "./components/cases/FinancialsTab";
import { OverviewTab } from "./components/cases/OverviewTab";
import { PipelineTab } from "./components/cases/PipelineTab";

export default function App() {
    // Initialize theme on mount (applies data-theme attribute to <html>)
    useTheme();

    // SEC-033: Fetch CSRF cookie from backend on startup
    useEffect(() => { initCSRF(); }, []);

    return (
        <ErrorBoundary fallbackTitle="Application Error">
            <BrowserRouter>
                <ShellContextProvider>
                    <Routes>
                        <Route element={<AppShell />}>
                            <Route index element={<DashboardView />} />

                            {/* Cases list */}
                            <Route path="cases" element={<CasesListView />} />

                            {/* Case detail with tabbed sub-routes */}
                            <Route path="cases/:caseId" element={<CaseDetailView />}>
                                <Route index element={<Navigate to="overview" replace />} />
                                <Route path="overview" element={<OverviewTab />} />
                                <Route path="documents" element={<DocumentsTab />} />
                                <Route path="pipeline" element={<PipelineTab />} />
                                <Route path="financials" element={<FinancialsTab />} />
                                <Route path="referrals" element={<ReferralsTab />} />
                                {/* Legacy routes — redirect to pipeline */}
                                <Route path="signals" element={<Navigate to="../pipeline" replace />} />
                                <Route path="detections" element={<Navigate to="../pipeline" replace />} />
                                <Route path="findings" element={<Navigate to="../pipeline" replace />} />
                            </Route>

                            <Route path="entities" element={<EntityBrowserView />} />
                            <Route path="entities/:entityType/:entityId" element={<EntityDetailView />} />
                            <Route path="triage" element={<TriageView />} />
                            <Route path="referrals" element={<ReferralsView />} />
                            <Route path="search" element={<SearchView />} />
                            <Route path="settings" element={<SettingsView />} />

                            {/* Catch-all redirect */}
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Route>
                    </Routes>
                </ShellContextProvider>
            </BrowserRouter>
        </ErrorBoundary>
    );
}
            