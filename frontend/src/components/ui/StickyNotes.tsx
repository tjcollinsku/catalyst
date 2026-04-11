import { useCallback, useEffect, useState } from "react";
import { InvestigatorNote } from "../../types";
import { createNote, deleteNote, fetchNotes } from "../../api";
import styles from "./StickyNotes.module.css";

interface StickyNotesProps {
    caseId: string;
    targetType: string;
    targetId: string;
    compact?: boolean;
}

export function StickyNotes({
    caseId,
    targetType,
    targetId,
    compact = false,
}: StickyNotesProps): JSX.Element {
    const [notes, setNotes] = useState<InvestigatorNote[]>([]);
    const [newNoteContent, setNewNoteContent] = useState("");
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isExpanded, setIsExpanded] = useState(!compact);
    const [isSaving, setIsSaving] = useState(false);

    // Fetch notes on mount and when target changes
    useEffect(() => {
        const loadNotes = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const result = await fetchNotes(caseId, targetType, targetId);
                setNotes(result.results);
            } catch (err) {
                const message =
                    err instanceof Error ? err.message : "Failed to load notes";
                setError(message);
                console.error("Error fetching notes:", err);
            } finally {
                setIsLoading(false);
            }
        };

        loadNotes();
    }, [caseId, targetType, targetId]);

    const handleAddNote = useCallback(async () => {
        if (!newNoteContent.trim()) {
            return;
        }

        setIsSaving(true);
        setError(null);
        try {
            const newNote = await createNote(
                caseId,
                targetType,
                targetId,
                newNoteContent
            );
            setNotes((prev) => [newNote, ...prev]);
            setNewNoteContent("");
        } catch (err) {
            const message =
                err instanceof Error ? err.message : "Failed to save note";
            setError(message);
            console.error("Error creating note:", err);
        } finally {
            setIsSaving(false);
        }
    }, [caseId, targetType, targetId, newNoteContent]);

    const handleDeleteNote = useCallback(
        async (noteId: string) => {
            setError(null);
            try {
                await deleteNote(caseId, noteId);
                setNotes((prev) => prev.filter((note) => note.id !== noteId));
            } catch (err) {
                const message =
                    err instanceof Error
                        ? err.message
                        : "Failed to delete note";
                setError(message);
                console.error("Error deleting note:", err);
            }
        },
        [caseId]
    );

    const formatTimestamp = (isoString: string): string => {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return "just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        });
    };

    // Compact mode: show a pill with note count
    if (compact && !isExpanded) {
        return (
            <button
                className={styles.compactPill}
                onClick={() => setIsExpanded(true)}
                type="button"
            >
                <span className={styles.noteIcon}>📝</span>
                <span className={styles.noteCount}>{notes.length}</span>
            </button>
        );
    }

    return (
        <div className={styles.container}>
            {compact && (
                <button
                    className={styles.collapseButton}
                    onClick={() => setIsExpanded(false)}
                    type="button"
                    title="Collapse notes"
                >
                    ✕
                </button>
            )}

            <div className={styles.notesList}>
                {isLoading ? (
                    <div className={styles.loadingState}>Loading notes...</div>
                ) : error ? (
                    <div className={styles.errorState}>{error}</div>
                ) : notes.length === 0 ? (
                    <div className={styles.emptyState}>
                        No notes yet. Start writing!
                    </div>
                ) : (
                    notes.map((note) => (
                        <div key={note.id} className={styles.note}>
                            <p className={styles.noteContent}>
                                {note.content}
                            </p>
                            <div className={styles.noteFooter}>
                                <span className={styles.noteTimestamp}>
                                    {formatTimestamp(note.created_at)}
                                </span>
                                <button
                                    className={styles.deleteButton}
                                    onClick={() => handleDeleteNote(note.id)}
                                    type="button"
                                    title="Delete note"
                                    aria-label="Delete note"
                                >
                                    ×
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </div>

            <div className={styles.addNoteArea}>
                <textarea
                    className={styles.noteTextarea}
                    placeholder="Write a note about this document..."
                    value={newNoteContent}
                    onChange={(e) => setNewNoteContent(e.target.value)}
                    disabled={isSaving}
                />
                <button
                    className={styles.saveButton}
                    onClick={handleAddNote}
                    disabled={!newNoteContent.trim() || isSaving}
                    type="button"
                >
                    {isSaving ? "Saving..." : "Save"}
                </button>
            </div>
        </div>
    );
}
