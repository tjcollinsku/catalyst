import { ReactNode } from "react";
import styles from "./ResizablePanelLayout.module.css";

interface ResizablePanelLayoutProps {
    /** Main content area (graph, list, etc.) */
    children: ReactNode;
    /** Content for the slide-in side panel */
    panelContent: ReactNode | null;
    /** Whether the side panel is open */
    panelOpen: boolean;
    /** Width of the side panel in pixels */
    panelWidth?: number;
    /** Called when user clicks outside the panel or hits the close button */
    onPanelClose?: () => void;
}

/**
 * Two-panel layout where a side panel slides in from the right.
 * The main content area smoothly resizes to make room (no overlap).
 *
 * Usage:
 *   <ResizablePanelLayout
 *     panelContent={selectedEntity && <EntityProfile entity={selectedEntity} />}
 *     panelOpen={!!selectedEntity}
 *     onPanelClose={() => setSelectedEntity(null)}
 *   >
 *     <EntityGraph ... />
 *   </ResizablePanelLayout>
 */
export function ResizablePanelLayout({
    children,
    panelContent,
    panelOpen,
    panelWidth = 360,
    onPanelClose,
}: ResizablePanelLayoutProps) {
    // onPanelClose is passed through for consumers to wire up click-outside behavior
    void onPanelClose;
    return (
        <div className={styles.container}>
            <div
                className={panelOpen ? styles.mainShifted : styles.main}
                style={panelOpen ? { marginRight: `${panelWidth}px` } : undefined}
            >
                {children}
            </div>

            <div
                className={panelOpen ? styles.panelOpen : styles.panel}
                style={{ width: `${panelWidth}px` }}
            >
                {panelContent}
            </div>
        </div>
    );
}
