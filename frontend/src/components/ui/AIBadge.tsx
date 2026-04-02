import { useState } from "react";
import styles from "./AIBadge.module.css";

/* ── Types ────────────────────────────────────────────── */

type AIBadgeState = "idle" | "loading" | "loaded" | "error";

interface AIBadgeProps {
    /** One-line AI summary shown when collapsed */
    summary: string;
    /** Full AI analysis shown when expanded (optional) */
    detail?: string;
    /** Current loading state */
    state?: AIBadgeState;
    /** Called when the badge is clicked (e.g. to fetch full analysis) */
    onClick?: () => void;
}

/**
 * Inline AI suggestion badge for signal cards, detection cards, and entity profiles.
 * Shows a one-line summary with a robot icon. Click to expand full analysis.
 *
 * States:
 *   - loading: shimmer animation while AI responds
 *   - loaded: summary text (click to expand detail)
 *   - error: "AI unavailable" message
 *   - idle: hidden (returns null)
 *
 * Usage:
 *   <AIBadge
 *     summary="Pattern matches rapid-flip scheme seen in 3 prior cases."
 *     detail="Cross-reference with SR-018 (Related Party TX). The property at
 *             123 Main St was transferred twice within 90 days..."
 *     state="loaded"
 *   />
 */
export function AIBadge({
    summary,
    detail,
    state = "loaded",
    onClick,
}: AIBadgeProps) {
    const [expanded, setExpanded] = useState(false);

    if (state === "idle") return null;

    if (state === "loading") {
        return (
            <div className={styles.loading}>
                <span className={styles.icon} aria-hidden="true">{"\uD83E\uDD16"}</span>
                <div className={styles.shimmer} />
            </div>
        );
    }

    if (state === "error") {
        return (
            <div className={styles.error}>
                <span className={styles.icon} aria-hidden="true">{"\uD83E\uDD16"}</span>
                <span className={styles.errorText}>AI unavailable</span>
            </div>
        );
    }

    function handleClick() {
        if (detail) {
            setExpanded((prev) => !prev);
        }
        onClick?.();
    }

    return (
        <div
            className={styles.badge}
            onClick={handleClick}
            role={detail ? "button" : undefined}
            tabIndex={detail ? 0 : undefined}
            onKeyDown={(e) => {
                if (detail && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    handleClick();
                }
            }}
        >
            <span className={styles.icon} aria-hidden="true">{"\uD83E\uDD16"}</span>
            <div className={styles.content}>
                <p className={expanded ? styles.summary : styles.summaryCollapsed}>
                    {summary}
                </p>
                {expanded && detail && (
                    <p className={styles.detail}>{detail}</p>
                )}
                {!expanded && detail && (
                    <span className={styles.expandHint}>Click to expand</span>
                )}
            </div>
        </div>
    );
}
