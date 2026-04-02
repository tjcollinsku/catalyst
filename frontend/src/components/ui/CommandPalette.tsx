import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import styles from "./CommandPalette.module.css";

interface CommandItem {
    id: string;
    label: string;
    shortcut?: string;
    icon: string;
    action: () => void;
}

interface CommandPaletteProps {
    isOpen: boolean;
    onClose: () => void;
}

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
    const navigate = useNavigate();
    const inputRef = useRef<HTMLInputElement>(null);
    const [query, setQuery] = useState("");
    const [selectedIndex, setSelectedIndex] = useState(0);

    const commands: CommandItem[] = [
        { id: "dashboard", label: "Go to Dashboard", shortcut: "G D", icon: "\u2593", action: () => navigate("/") },
        { id: "cases", label: "Go to Cases", shortcut: "G C", icon: "\uD83D\uDCC1", action: () => navigate("/cases") },
        { id: "entities", label: "Go to Entities", shortcut: "G E", icon: "\uD83D\uDC64", action: () => navigate("/entities") },
        { id: "triage", label: "Go to Triage", shortcut: "G T", icon: "\u26A1", action: () => navigate("/triage") },
        { id: "referrals", label: "Go to Referrals", shortcut: "G R", icon: "\uD83D\uDCE4", action: () => navigate("/referrals") },
        { id: "search", label: "Go to Search", shortcut: "G S", icon: "\uD83D\uDD0D", action: () => navigate("/search") },
        { id: "settings", label: "Go to Settings", icon: "\u2699\uFE0F", action: () => navigate("/settings") },
        { id: "new-case", label: "Create New Case", icon: "\u2795", action: () => navigate("/cases") },
    ];

    const filtered = query.trim()
        ? commands.filter((c) =>
            c.label.toLowerCase().includes(query.toLowerCase()),
        )
        : commands;

    // Reset selection when filter changes
    useEffect(() => {
        setSelectedIndex(0);
    }, [query]);

    // Focus input when opened
    useEffect(() => {
        if (isOpen) {
            setQuery("");
            setSelectedIndex(0);
            // Use a short timeout to wait for animation
            const t = setTimeout(() => inputRef.current?.focus(), 50);
            return () => clearTimeout(t);
        }
    }, [isOpen]);

    const executeCommand = useCallback(
        (cmd: CommandItem) => {
            cmd.action();
            onClose();
        },
        [onClose],
    );

    function handleKeyDown(e: React.KeyboardEvent) {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setSelectedIndex((i) => Math.max(i - 1, 0));
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (filtered[selectedIndex]) {
                executeCommand(filtered[selectedIndex]);
            }
        } else if (e.key === "Escape") {
            onClose();
        }
    }

    if (!isOpen) return null;

    return (
        <div
            className={styles.backdrop}
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
        >
            <div
                className={styles.palette}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={handleKeyDown}
            >
                <div className={styles.inputRow}>
                    <span className={styles.icon}>{"\u2318"}</span>
                    <input
                        ref={inputRef}
                        type="text"
                        className={styles.input}
                        placeholder="Type a command..."
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        aria-label="Search commands"
                    />
                </div>

                <ul className={styles.list} role="listbox">
                    {filtered.map((cmd, i) => (
                        <li
                            key={cmd.id}
                            className={i === selectedIndex ? styles.itemSelected : styles.item}
                            role="option"
                            aria-selected={i === selectedIndex}
                            onClick={() => executeCommand(cmd)}
                            onMouseEnter={() => setSelectedIndex(i)}
                        >
                            <span className={styles.itemIcon}>{cmd.icon}</span>
                            <span className={styles.itemLabel}>{cmd.label}</span>
                            {cmd.shortcut && (
                                <kbd className={styles.itemShortcut}>{cmd.shortcut}</kbd>
                            )}
                        </li>
                    ))}
                    {filtered.length === 0 && (
                        <li className={styles.empty}>No matching commands</li>
                    )}
                </ul>
            </div>
        </div>
    );
}
