import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "dark" | "light" | "auto";

const STORAGE_KEY = "catalyst-theme";

function getInitialTheme(): ThemeMode {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === "dark" || stored === "light" || stored === "auto") {
            return stored;
        }
    } catch {
        // localStorage unavailable
    }
    return "dark";
}

export function useTheme() {
    const [theme, setThemeState] = useState<ThemeMode>(getInitialTheme);

    const setTheme = useCallback((next: ThemeMode) => {
        setThemeState(next);
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch {
            // localStorage unavailable
        }

        // Trigger smooth color transition
        const html = document.documentElement;
        html.setAttribute("data-theme-transitioning", "");
        requestAnimationFrame(() => {
            html.setAttribute("data-theme", next);
            setTimeout(() => {
                html.removeAttribute("data-theme-transitioning");
            }, 250);
        });
    }, []);

    useEffect(() => {
        document.documentElement.setAttribute("data-theme", theme);
    }, [theme]);

    return { theme, setTheme } as const;
}
