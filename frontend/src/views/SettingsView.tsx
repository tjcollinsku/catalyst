import { useCallback, useState } from "react";
import styles from "./SettingsView.module.css";
import { useTheme, ThemeMode } from "../hooks/useTheme";
import { ExternalSearchLauncher } from "../types";
import {
    loadLaunchers,
    saveLaunchers,
    resetLaunchersToDefaults,
} from "../data/externalSearchLaunchers";

type SettingsSection = "appearance" | "keyboard" | "external-search" | "about";

const NAV_ITEMS: { key: SettingsSection; label: string; icon: string }[] = [
    { key: "appearance", label: "Appearance", icon: "\uD83C\uDFA8" },
    { key: "keyboard", label: "Keyboard", icon: "\u2328\uFE0F" },
    { key: "external-search", label: "External Search", icon: "\uD83D\uDD0E" },
    { key: "about", label: "About", icon: "\u2139\uFE0F" },
];

const SHORTCUTS: { keys: string; action: string }[] = [
    { keys: "\u2318K / Ctrl+K", action: "Focus search bar" },
    { keys: "Escape", action: "Close search / modal / panel" },
    { keys: "G then D", action: "Go to Dashboard" },
    { keys: "G then C", action: "Go to Cases" },
    { keys: "G then E", action: "Go to Entities" },
    { keys: "G then T", action: "Go to Triage" },
    { keys: "G then R", action: "Go to Referrals" },
    { keys: "G then S", action: "Go to Settings" },
];

export function SettingsView() {
    const { theme, setTheme } = useTheme();
    const [activeSection, setActiveSection] = useState<SettingsSection>("appearance");
    const [launchers, setLaunchers] = useState<ExternalSearchLauncher[]>(loadLaunchers);
    const [editingLauncher, setEditingLauncher] = useState<ExternalSearchLauncher | null>(null);
    const [newName, setNewName] = useState("");
    const [newUrl, setNewUrl] = useState("");

    const themeOptions: { value: ThemeMode; label: string; desc: string }[] = [
        { value: "dark", label: "Dark", desc: "Dark background (default)" },
        { value: "light", label: "Light", desc: "Light background" },
        { value: "auto", label: "Auto", desc: "Follow system preference" },
    ];

    const handleSaveLaunchers = useCallback((updated: ExternalSearchLauncher[]) => {
        setLaunchers(updated);
        saveLaunchers(updated);
    }, []);

    function handleAddLauncher() {
        if (!newName.trim() || !newUrl.trim()) return;
        const launcher: ExternalSearchLauncher = {
            id: `custom-${Date.now()}`,
            name: newName.trim(),
            urlTemplate: newUrl.trim(),
        };
        handleSaveLaunchers([...launchers, launcher]);
        setNewName("");
        setNewUrl("");
    }

    function handleRemoveLauncher(id: string) {
        handleSaveLaunchers(launchers.filter((l) => l.id !== id));
    }

    function handleEditLauncher(launcher: ExternalSearchLauncher) {
        setEditingLauncher(launcher);
        setNewName(launcher.name);
        setNewUrl(launcher.urlTemplate);
    }

    function handleSaveEdit() {
        if (!editingLauncher || !newName.trim() || !newUrl.trim()) return;
        handleSaveLaunchers(
            launchers.map((l) =>
                l.id === editingLauncher.id
                    ? { ...l, name: newName.trim(), urlTemplate: newUrl.trim() }
                    : l,
            ),
        );
        setEditingLauncher(null);
        setNewName("");
        setNewUrl("");
    }

    function handleResetLaunchers() {
        const defaults = resetLaunchersToDefaults();
        setLaunchers(defaults);
    }

    return (
        <div className={styles.settingsLayout}>
            {/* Sub-navigation */}
            <nav className={styles.settingsNav}>
                {NAV_ITEMS.map((item) => (
                    <button
                        key={item.key}
                        className={`${styles.settingsNavItem} ${activeSection === item.key ? styles.active : ""}`}
                        onClick={() => setActiveSection(item.key)}
                    >
                        <span>{item.icon}</span>
                        {item.label}
                    </button>
                ))}
            </nav>

            {/* Content */}
            <div className={styles.settingsContent}>
                {/* ── Appearance ── */}
                {activeSection === "appearance" && (
                    <>
                        <h2>Appearance</h2>

                        <section className={`${styles.infoCard} ${styles.settingsCard}`}>
                            <h3>Theme</h3>
                            <div className={styles.settingsThemeOptions}>
                                {themeOptions.map((opt) => (
                                    <button
                                        key={opt.value}
                                        onClick={() => setTheme(opt.value)}
                                        className={`${styles.settingsThemeBtn} ${theme === opt.value ? styles.active : ""}`}
                                        title={opt.desc}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                            <p className={styles.settingsHint}>{themeOptions.find((o) => o.value === theme)?.desc}</p>
                        </section>
                    </>
                )}

                {/* ── Keyboard ── */}
                {activeSection === "keyboard" && (
                    <>
                        <h2>Keyboard Shortcuts</h2>

                        <section className={`${styles.infoCard} ${styles.settingsCard}`}>
                            <table className={styles.shortcutsTable}>
                                <thead>
                                    <tr>
                                        <th>Keys</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {SHORTCUTS.map((s) => (
                                        <tr key={s.keys}>
                                            <td>
                                                <kbd>{s.keys}</kbd>
                                            </td>
                                            <td>{s.action}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </section>
                    </>
                )}

                {/* ── External Search ── */}
                {activeSection === "external-search" && (
                    <>
                        <h2>External Search Launchers</h2>
                        <p className={styles.settingsDesc}>
                            These open in a new browser tab with the entity name pre-filled. Use{" "}
                            <code>{"{q}"}</code> as the query placeholder in the URL template.
                        </p>

                        <section className={`${styles.infoCard} ${styles.settingsCard}`}>
                            <table className={styles.launcherTable}>
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>URL Template</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {launchers.map((l) => (
                                        <tr key={l.id}>
                                            <td>{l.name}</td>
                                            <td className={styles.launcherUrlCell}>
                                                <code>{l.urlTemplate}</code>
                                            </td>
                                            <td className={styles.launcherActions}>
                                                <button
                                                    className={styles.launcherActionBtn}
                                                    onClick={() => handleEditLauncher(l)}
                                                >
                                                    Edit
                                                </button>
                                                <button
                                                    className={`${styles.launcherActionBtn} ${styles.danger}`}
                                                    onClick={() => handleRemoveLauncher(l.id)}
                                                >
                                                    Remove
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            {/* Add / edit form */}
                            <div className={styles.launcherForm}>
                                <input
                                    type="text"
                                    className={styles.formInput}
                                    placeholder="Source name"
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                />
                                <input
                                    type="text"
                                    className={styles.formInput}
                                    placeholder="URL with {q} placeholder"
                                    value={newUrl}
                                    onChange={(e) => setNewUrl(e.target.value)}
                                />
                                {editingLauncher ? (
                                    <>
                                        <button className={styles.btnPrimary} onClick={handleSaveEdit}>
                                            Save Edit
                                        </button>
                                        <button
                                            className={styles.btnSecondary}
                                            onClick={() => {
                                                setEditingLauncher(null);
                                                setNewName("");
                                                setNewUrl("");
                                            }}
                                        >
                                            Cancel
                                        </button>
                                    </>
                                ) : (
                                    <button className={styles.btnPrimary} onClick={handleAddLauncher}>
                                        + Add Source
                                    </button>
                                )}
                            </div>

                            <div className={styles.launcherReset}>
                                <button className={styles.btnSecondary} onClick={handleResetLaunchers}>
                                    Reset to Defaults
                                </button>
                            </div>
                        </section>
                    </>
                )}

                {/* ── About ── */}
                {activeSection === "about" && (
                    <>
                        <h2>About Catalyst</h2>

                        <section className={`${styles.infoCard} ${styles.settingsCard}`}>
                            <dl className={styles.aboutFields}>
                                <dt>Version</dt>
                                <dd>0.1.0-alpha</dd>
                                <dt>Purpose</dt>
                                <dd>
                                    Investigation intelligence platform for fraud pattern detection
                                    with defensible audit history and human-in-the-loop evidence workflows.
                                </dd>
                                <dt>Frontend</dt>
                                <dd>React 18 + TypeScript 5.6 + Vite 5</dd>
                                <dt>Backend</dt>
                                <dd>Django 5 + PostgreSQL 16</dd>
                                <dt>Signal Rules</dt>
                                <dd>10 rules (SR-001 through SR-010)</dd>
                                <dt>Entity Types</dt>
                                <dd>Person, Organization, Property, Financial Instrument</dd>
                            </dl>
                        </section>
                    </>
                )}
            </div>
        </div>
    );
}
