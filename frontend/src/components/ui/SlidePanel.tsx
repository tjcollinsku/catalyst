import { ReactNode, useState } from "react";
import styles from "./SlidePanel.module.css";

/* ── Expandable section sub-component ────────────────── */

interface SlidePanelSectionProps {
    title: string;
    count?: number;
    defaultOpen?: boolean;
    children: ReactNode;
}

export function SlidePanelSection({
    title,
    count,
    defaultOpen = false,
    children,
}: SlidePanelSectionProps) {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <div className={styles.section}>
            <button
                type="button"
                className={styles.sectionToggle}
                onClick={() => setOpen((prev) => !prev)}
                aria-expanded={open}
            >
                <span>
                    {title}
                    {count !== undefined && (
                        <span className={styles.sectionCount}>({count})</span>
                    )}
                </span>
                <span className={open ? styles.sectionArrowOpen : styles.sectionArrow}>
                    {"\u25B6"}
                </span>
            </button>
            {open && <div className={styles.sectionContent}>{children}</div>}
        </div>
    );
}

/* ── Main SlidePanel component ───────────────────────── */

interface SlidePanelProps {
    /** Panel title */
    title: string;
    /** Optional subtitle below title */
    subtitle?: string;
    /** Panel body content */
    children: ReactNode;
    /** Called when close button is clicked */
    onClose: () => void;
    /** Optional footer content (e.g. "View Full Profile" link) */
    footer?: ReactNode;
}

/**
 * Generic slide-in panel with header, scrollable body, and optional footer.
 * Designed to sit inside a ResizablePanelLayout's panel slot.
 *
 * Usage:
 *   <SlidePanel title="Jay Brunswick" subtitle="Person · President" onClose={handleClose}>
 *     <SlidePanelSection title="Organizations" count={2} defaultOpen>
 *       <OrgList orgs={entity.orgs} />
 *     </SlidePanelSection>
 *     <SlidePanelSection title="Signals" count={4}>
 *       <SignalList signals={entity.signals} />
 *     </SlidePanelSection>
 *   </SlidePanel>
 */
export function SlidePanel({
    title,
    subtitle,
    children,
    onClose,
    footer,
}: SlidePanelProps) {
    return (
        <div className={styles.panel}>
            <div className={styles.header}>
                <div>
                    <h3 className={styles.title}>{title}</h3>
                    {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
                </div>
                <button
                    type="button"
                    className={styles.closeBtn}
                    onClick={onClose}
                    aria-label="Close panel"
                >
                    {"\u2715"}
                </button>
            </div>

            <div className={styles.body}>{children}</div>

            {footer && <div className={styles.footer}>{footer}</div>}
        </div>
    );
}
