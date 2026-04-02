import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchSignalSummary, fetchCrossCaseReferrals, isAbortError } from "../api";

interface ShellState {
    /** Display name of the currently viewed case (set by CaseDetailView) */
    caseName: string | null;
    /** Number of open signals across all cases */
    triageCount: number;
    /** Number of draft referrals across all cases */
    draftReferralCount: number;
    /** Update the case name shown in the breadcrumb */
    setCaseName: (name: string | null) => void;
    /** Force a refresh of badge counts */
    refreshBadges: () => void;
}

const ShellContext = createContext<ShellState>({
    caseName: null,
    triageCount: 0,
    draftReferralCount: 0,
    setCaseName: () => {},
    refreshBadges: () => {},
});

export function useShellContext() {
    return useContext(ShellContext);
}

export function ShellContextProvider({ children }: { children: React.ReactNode }) {
    const [caseName, setCaseName] = useState<string | null>(null);
    const [triageCount, setTriageCount] = useState(0);
    const [draftReferralCount, setDraftReferralCount] = useState(0);

    const loadBadges = useCallback(async (signal?: AbortSignal) => {
        try {
            const [summaryRes, referralsRes] = await Promise.all([
                fetchSignalSummary(signal ? { signal } : undefined),
                fetchCrossCaseReferrals({ status: "DRAFT" }, 1, 0, signal ? { signal } : undefined),
            ]);
            if (!signal?.aborted) {
                const openTotal = summaryRes.results.reduce((sum, s) => sum + s.open_count, 0);
                setTriageCount(openTotal);
                setDraftReferralCount(referralsRes.count);
            }
        } catch (err) {
            if (!isAbortError(err)) console.warn("Badge count fetch failed:", err);
        }
    }, []);

    // Load on mount, then every 60s
    useEffect(() => {
        const controller = new AbortController();
        void loadBadges(controller.signal);
        const interval = setInterval(() => void loadBadges(), 60_000);
        return () => {
            controller.abort();
            clearInterval(interval);
        };
    }, [loadBadges]);

    const refreshBadges = useCallback(() => void loadBadges(), [loadBadges]);

    return (
        <ShellContext.Provider
            value={{ caseName, triageCount, draftReferralCount, setCaseName, refreshBadges }}
        >
            {children}
        </ShellContext.Provider>
    );
}
