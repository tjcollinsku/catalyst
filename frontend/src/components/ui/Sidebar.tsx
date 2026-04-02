import { NavLink } from "react-router-dom";
import styles from "./Sidebar.module.css";

interface NavItem {
    to: string;
    icon: string;
    label: string;
    badge?: number;
    badgeColor?: "red" | "blue";
}

const mainNav: NavItem[] = [
    { to: "/", icon: "\u2593", label: "Dashboard" },
    { to: "/cases", icon: "\uD83D\uDCC1", label: "Cases" },
    { to: "/entities", icon: "\uD83D\uDC64", label: "Entities" },
    { to: "/triage", icon: "\u26A1", label: "Triage" },
    { to: "/referrals", icon: "\uD83D\uDCE4", label: "Referrals" },
    { to: "/search", icon: "\uD83D\uDD0D", label: "Search" },
];

const footerNav: NavItem[] = [
    { to: "/settings", icon: "\u2699\uFE0F", label: "Settings" },
];

interface SidebarProps {
    triageCount?: number;
    draftReferralCount?: number;
}

export function Sidebar({ triageCount, draftReferralCount }: SidebarProps) {
    function renderLink(item: NavItem) {
        let badge = item.badge;
        let badgeColor = item.badgeColor;

        if (item.to === "/triage" && triageCount && triageCount > 0) {
            badge = triageCount;
            badgeColor = "red";
        }
        if (item.to === "/referrals" && draftReferralCount && draftReferralCount > 0) {
            badge = draftReferralCount;
            badgeColor = "blue";
        }

        return (
            <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                    isActive ? styles.linkActive : styles.link
                }
            >
                <span className={styles.linkIcon}>{item.icon}</span>
                <span className={styles.linkLabel}>{item.label}</span>
                {badge !== undefined && badge > 0 && (
                    <span className={badgeColor === "red" ? styles.badgeRed : styles.badgeBlue}>
                        {badge}
                    </span>
                )}
            </NavLink>
        );
    }

    return (
        <aside className={styles.root} role="complementary" aria-label="Main navigation">
            <div className={styles.brand} aria-hidden="true">
                <span className={styles.brandIcon}>{"\u25C6"}</span>
                <span>CATALYST</span>
            </div>

            <nav className={styles.nav} aria-label="Primary">
                <div className={styles.navMain}>
                    {mainNav.map(renderLink)}
                </div>

                <div className={styles.divider} role="separator" />

                <div className={styles.navFooter}>
                    {footerNav.map(renderLink)}
                </div>
            </nav>

            <div className={styles.user} aria-label="Current user">
                <div className={styles.avatar} aria-hidden="true">TC</div>
                <div className={styles.userInfo}>
                    <span className={styles.userName}>Tyler Collins</span>
                    <span className={styles.userRole}>Investigator</span>
                </div>
            </div>
        </aside>
    );
}
