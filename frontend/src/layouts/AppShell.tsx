import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "../components/ui/Sidebar";
import { Breadcrumb } from "../components/ui/Breadcrumb";
import { CommandPalette } from "../components/ui/CommandPalette";
import { ToastItem, ToastStack } from "../components/ui/ToastStack";
import { AIAssistantPanel } from "../components/ai/AIAssistantPanel";
import { useShellContext } from "../contexts/ShellContext";
import { useTheme, ThemeMode } from "../hooks/useTheme";
import styles from "./AppShell.module.css";

const G_NAV_MAP: Record<string, string> = {
    d: "/",
    c: "/cases",
    e: "/entities",
    t: "/triage",
    r: "/referrals",
    s: "/settings",
};

export function AppShell() {
    const { caseName, triageCount } = useShellContext();
    const { theme, setTheme } = useTheme();

    const THEME_CYCLE: ThemeMode[] = ["dark", "light", "auto"];
    const THEME_ICON: Record<ThemeMode, string> = { dark: "\uD83C\uDF19", light: "\u2600\uFE0F", auto: "\uD83D\uDDA5\uFE0F" };
    const cycleTheme = () => {
        const idx = THEME_CYCLE.indexOf(theme);
        setTheme(THEME_CYCLE[(idx + 1) % THEME_CYCLE.length]);
    };
    const [toasts, setToasts] = useState<ToastItem[]>([]);
    const toastIdRef = useRef(0);
    const searchRef = useRef<HTMLInputElement>(null);
    const navigate = useNavigate();
    const location = useLocation();

    // Command palette
    const [paletteOpen, setPaletteOpen] = useState(false);

    // AI panel
    const [aiPanelOpen, setAiPanelOpen] = useState(false);

    // Extract caseId from URL path: /cases/:caseId/...
    const caseIdMatch = location.pathname.match(/^\/cases\/([^/]+)/);
    const activeCaseId = caseIdMatch ? caseIdMatch[1] : null;

    // G+key navigation state
    const gPressedRef = useRef(false);
    const gTimerRef = useRef<ReturnType<typeof setTimeout>>();

    const removeToast = useCallback((id: number) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const pushToast = useCallback((tone: "error" | "success", message: string) => {
        const id = ++toastIdRef.current;
        setToasts((prev) => [...prev, { id, tone, message }]);
        window.setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 3400);
    }, []);

    // Global keyboard shortcuts
    useEffect(() => {
        function isInputFocused() {
            const tag = document.activeElement?.tagName;
            return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
        }

        function onKeyDown(event: KeyboardEvent) {
            // Cmd+K → focus search
            if ((event.metaKey || event.ctrlKey) && event.key === "k") {
                event.preventDefault();
                searchRef.current?.focus();
                return;
            }

            // Cmd+Shift+P → command palette
            if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key === "p") {
                event.preventDefault();
                setPaletteOpen((open) => !open);
                return;
            }

            // Escape → close palette
            if (event.key === "Escape") {
                if (paletteOpen) {
                    setPaletteOpen(false);
                    return;
                }
            }

            // G+key navigation — only when no input is focused
            if (isInputFocused() || paletteOpen) return;

            if (event.key === "g" || event.key === "G") {
                if (!gPressedRef.current) {
                    gPressedRef.current = true;
                    clearTimeout(gTimerRef.current);
                    gTimerRef.current = setTimeout(() => {
                        gPressedRef.current = false;
                    }, 800);
                }
                return;
            }

            if (gPressedRef.current) {
                gPressedRef.current = false;
                clearTimeout(gTimerRef.current);
                const route = G_NAV_MAP[event.key.toLowerCase()];
                if (route) {
                    event.preventDefault();
                    navigate(route);
                }
            }
        }

        window.addEventListener("keydown", onKeyDown);
        return () => {
            window.removeEventListener("keydown", onKeyDown);
            clearTimeout(gTimerRef.current);
        };
    }, [navigate, paletteOpen]);

    function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
        if (event.key === "Enter") {
            const value = (event.target as HTMLInputElement).value.trim();
            if (value) {
                navigate(`/search?q=${encodeURIComponent(value)}`);
                (event.target as HTMLInputElement).blur();
            }
        }
        if (event.key === "Escape") {
            (event.target as HTMLInputElement).blur();
        }
    }

    return (
        <div className={styles.shell}>
            <a href="#main-content" className="skip-to-content">Skip to content</a>
            <Sidebar triageCount={triageCount} />

            <div className={styles.shellMain}>
                <header className={styles.topbar} role="banner">
                    <div className={styles.topbarRow}>
                        <div className={styles.topbarSearch}>
                            <span className={styles.searchIcon} aria-hidden="true">{"\uD83D\uDD0D"}</span>
                            <input
                                ref={searchRef}
                                type="text"
                                placeholder="Ask anything about your cases..."
                                onKeyDown={handleSearchKeyDown}
                                aria-label="Search cases, signals, entities"
                                className={styles.searchInput}
                            />
                            <span className={styles.searchHint} aria-hidden="true">
                                {navigator.platform?.includes("Mac") ? "\u2318K" : "Ctrl+K"}
                            </span>
                        </div>
                        <div className={styles.topbarActions}>
                            {activeCaseId && (
                                <button
                                    className={`${styles.aiToggle} ${aiPanelOpen ? styles.aiToggleActive : ""}`}
                                    onClick={() => setAiPanelOpen((v) => !v)}
                                    aria-label="Toggle AI assistant"
                                    title="AI Assistant (case-aware)"
                                >
                                    <span className={styles.aiToggleIcon}>✦</span>
                                    <span className={styles.aiToggleLabel}>AI</span>
                                </button>
                            )}
                            <button
                                className={styles.themeToggle}
                                onClick={cycleTheme}
                                aria-label={`Switch theme (current: ${theme})`}
                                title={`Theme: ${theme}`}
                            >
                                {THEME_ICON[theme]}
                            </button>
                            <button
                                className={styles.notificationBell}
                                aria-label="Notifications"
                            >
                                {"\uD83D\uDD14"}
                            </button>
                        </div>
                    </div>
                    <Breadcrumb caseName={caseName ?? undefined} />
                </header>

                <main id="main-content" className={styles.viewContent} role="main">
                    <Outlet context={{ pushToast }} />
                </main>

                <ToastStack toasts={toasts} onDismiss={removeToast} />
            </div>

            {activeCaseId && (
                <AIAssistantPanel
                    caseId={activeCaseId}
                    caseName={caseName ?? undefined}
                    open={aiPanelOpen}
                    onClose={() => setAiPanelOpen(false)}
                />
            )}

            <CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </div>
    );
}
