import { Link, useLocation, useParams } from "react-router-dom";
import styles from "./Breadcrumb.module.css";

interface CrumbDef {
    label: string;
    to?: string;
}

/**
 * Build breadcrumb trail from the current URL path.
 * Case names are resolved via the optional `caseName` prop
 * since the URL only contains the UUID.
 */
export function Breadcrumb({ caseName }: { caseName?: string }) {
    const location = useLocation();
    const params = useParams();
    const segments = location.pathname.split("/").filter(Boolean);

    const crumbs: CrumbDef[] = [];

    // Always start with the named top-level route
    if (segments.length === 0) {
        crumbs.push({ label: "Dashboard" });
    } else {
        const topLevel = segments[0];
        const topLabels: Record<string, string> = {
            cases: "Cases",
            entities: "Entities",
            triage: "Signal Triage",
            referrals: "Referrals",
            search: "Search",
            settings: "Settings",
        };

        const topLabel = topLabels[topLevel] ?? topLevel;

        if (segments.length === 1) {
            // Single-level route like /cases or /triage
            crumbs.push({ label: topLabel });
        } else {
            // Multi-level: make parent a link
            crumbs.push({ label: topLabel, to: `/${topLevel}` });

            if (topLevel === "cases" && params.caseId) {
                const displayName = caseName ?? "Case";

                // /cases/:caseId
                if (segments.length === 2) {
                    crumbs.push({ label: displayName });
                } else {
                    // /cases/:caseId/documents etc.
                    crumbs.push({ label: displayName, to: `/cases/${params.caseId}` });
                    const tabLabels: Record<string, string> = {
                        documents: "Documents",
                        signals: "Signals",
                        detections: "Detections",
                        referrals: "Referrals",
                        notes: "Notes",
                        timeline: "Timeline",
                    };
                    const tab = segments[2];
                    crumbs.push({ label: tabLabels[tab] ?? tab });
                }
            } else if (topLevel === "entities" && segments.length >= 3) {
                // /entities/:type/:id
                const typeLabel = segments[1].charAt(0).toUpperCase() + segments[1].slice(1);
                crumbs.push({ label: typeLabel });
            } else if (topLevel === "search") {
                const searchParams = new URLSearchParams(location.search);
                const query = searchParams.get("q");
                if (query) {
                    crumbs.push({ label: `"${query}"` });
                }
            }
        }
    }

    return (
        <nav className={styles.breadcrumb} aria-label="Breadcrumb">
            {crumbs.map((crumb, index) => {
                const isLast = index === crumbs.length - 1;
                return (
                    <span key={index}>
                        {index > 0 && <span className={styles.separator}>{"\u203A"}</span>}
                        {" "}
                        {crumb.to && !isLast ? (
                            <Link to={crumb.to}>{crumb.label}</Link>
                        ) : (
                            <span className={isLast ? styles.current : ""}>{crumb.label}</span>
                        )}
                    </span>
                );
            })}
        </nav>
    );
}
