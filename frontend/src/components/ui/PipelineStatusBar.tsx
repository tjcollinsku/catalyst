import styles from "./PipelineStatusBar.module.css";

/* ── Stage definition ────────────────────────────────── */

export interface PipelineStage {
    /** Unique key for filtering */
    key: string;
    /** Display label */
    label: string;
    /** Icon/emoji shown before label */
    icon: string;
    /** Number of items at this stage */
    count: number;
    /** CSS class key for the count badge color */
    colorClass: "countNew" | "countReviewing" | "countConfirmed" | "countDraft" | "countPublished";
}

/** Default investigation pipeline stages */
export const DEFAULT_STAGES: PipelineStage[] = [
    { key: "new", label: "New", icon: "\u26A1", count: 0, colorClass: "countNew" },
    { key: "reviewing", label: "Reviewing", icon: "\uD83D\uDD0D", count: 0, colorClass: "countReviewing" },
    { key: "confirmed", label: "Confirmed", icon: "\u2713", count: 0, colorClass: "countConfirmed" },
    { key: "draft", label: "Draft", icon: "\uD83D\uDCDD", count: 0, colorClass: "countDraft" },
    { key: "published", label: "Published", icon: "\uD83D\uDCCB", count: 0, colorClass: "countPublished" },
];

/* ── Component ───────────────────────────────────────── */

interface PipelineStatusBarProps {
    /** Pipeline stages with counts */
    stages: PipelineStage[];
    /** Currently active/selected stage key, or null for "All" */
    activeStage: string | null;
    /** Called when a stage is clicked */
    onStageClick: (stageKey: string | null) => void;
}

/**
 * Horizontal pipeline status bar showing investigation stages.
 * Click a stage to filter the list below to that stage's items.
 * Click "All" to show everything.
 *
 * ```
 * ┌───────────────────────────────────────────────────────────────┐
 * │ All │ ⚡ New (12) → 🔍 Reviewing (5) → ✓ Confirmed (3) → ...│
 * └───────────────────────────────────────────────────────────────┘
 * ```
 */
export function PipelineStatusBar({
    stages,
    activeStage,
    onStageClick,
}: PipelineStatusBarProps) {
    return (
        <div className={styles.bar} role="tablist" aria-label="Investigation pipeline stages">
            {/* "All" button */}
            <button
                type="button"
                className={activeStage === null ? styles.allBtnActive : styles.allBtn}
                onClick={() => onStageClick(null)}
                role="tab"
                aria-selected={activeStage === null}
            >
                All
            </button>

            {stages.map((stage, i) => (
                <div key={stage.key} style={{ display: "flex", alignItems: "stretch" }}>
                    {/* Arrow between stages */}
                    {i === 0 && <span className={styles.arrow} aria-hidden="true">{"\u2502"}</span>}

                    <button
                        type="button"
                        className={activeStage === stage.key ? styles.stageActive : styles.stage}
                        onClick={() => onStageClick(stage.key)}
                        role="tab"
                        aria-selected={activeStage === stage.key}
                    >
                        <span className={styles.stageIcon} aria-hidden="true">{stage.icon}</span>
                        <span className={styles.stageLabel}>{stage.label}</span>
                        <span className={`${styles.count} ${stage.count > 0 ? styles[stage.colorClass] : ""}`}>
                            {stage.count}
                        </span>
                    </button>

                    {/* Arrow connector after each stage except the last */}
                    {i < stages.length - 1 && (
                        <span className={styles.arrow} aria-hidden="true">{"\u2192"}</span>
                    )}
                </div>
            ))}
        </div>
    );
}
