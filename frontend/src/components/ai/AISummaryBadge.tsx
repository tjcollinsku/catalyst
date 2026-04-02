import { useCallback, useState } from "react";
import type { AISummarizeResponse } from "../../types";
import { aiSummarize } from "../../api";
import styles from "./AISummaryBadge.module.css";

interface AISummaryBadgeProps {
    caseId: string;
    targetType: string;
    targetId: string;
    /** Compact mode shows just the icon; full mode shows "AI Summary" label */
    compact?: boolean;
}

type BadgeState = "idle" | "loading" | "loaded" | "error";

export function AISummaryBadge({
    caseId,
    targetType,
    targetId,
    compact = false,
}: AISummaryBadgeProps) {
    const [state, setState] = useState<BadgeState>("idle");
    const [data, setData] = useState<AISummarizeResponse | null>(null);
    const [expanded, setExpanded] = useState(false);
    const [error, setError] = useState("");

    const fetchSummary = useCallback(async () => {
        if (state === "loading") return;
        if (state === "loaded") {
            setExpanded((v) => !v);
            return;
        }
        setState("loading");
        try {
            const result = await aiSummarize(caseId, targetType, targetId);
            setData(result);
            setState("loaded");
            setExpanded(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : "AI request failed");
            setState("error");
        }
    }, [caseId, targetType, targetId, state]);

    return (
        <div className={styles.wrapper}>
            <button
                className={`${styles.badge} ${styles[state]}`}
                onClick={fetchSummary}
                title={state === "loaded" ? "Toggle AI summary" : "Get AI summary"}
            >
                <span className={styles.icon}>
                    {state === "loading" ? (
                        <span className={styles.spinner} />
                    ) : (
                        "✦"
                    )}
                </span>
                {!compact && (
                    <span className={styles.label}>
                        {state === "loading"
                            ? "Analyzing…"
                            : state === "loaded"
                            ? "AI Summary"
                            : state === "error"
                            ? "Retry"
                            : "AI Summary"}
                    </span>
                )}
            </button>

            {state === "error" && (
                <div className={styles.errorTip}>{error}</div>
            )}

            {expanded && data && (
                <div className={styles.panel}>
                    <p className={styles.summaryText}>{data.summary}</p>

                    {data.key_facts.length > 0 && (
                        <div className={styles.section}>
                            <span className={styles.sectionLabel}>Key Facts</span>
                            <ul className={styles.factList}>
                                {data.key_facts.map((f, i) => (
                                    <li key={i}>{f}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {data.risk_indicators.length > 0 && (
                        <div className={styles.section}>
                            <span className={styles.sectionLabel}>Risk Indicators</span>
                            <ul className={styles.riskList}>
                                {data.risk_indicators.map((r, i) => (
                                    <li key={i}>{r}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className={styles.confidence}>
                        <span className={styles.confLabel}>Confidence</span>
                        <div className={styles.confBar}>
                            <div
                                className={styles.confFill}
                                style={{ width: `${Math.round(data.confidence * 100)}%` }}
                            />
                        </div>
                        <span className={styles.confValue}>
                            {Math.round(data.confidence * 100)}%
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
}
