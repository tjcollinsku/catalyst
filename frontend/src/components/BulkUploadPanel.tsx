import { useRef, useState } from "react";
import { BulkUploadResult } from "../api";
import { Button } from "./ui/Button";

const MAX_FILES = 50;

interface FileEntry {
    file: File;
    status: "pending" | "done" | "error";
    error?: string;
}

interface BulkUploadPanelProps {
    onUpload: (files: File[]) => Promise<BulkUploadResult>;
    onComplete: (result: BulkUploadResult) => void;
}

export function BulkUploadPanel({ onUpload, onComplete }: BulkUploadPanelProps) {
    const [entries, setEntries] = useState<FileEntry[]>([]);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    function addFiles(incoming: FileList | File[]) {
        const next = Array.from(incoming).map((file) => ({
            file,
            status: "pending" as const,
        }));
        setEntries((prev) => {
            const existing = new Set(prev.map((e) => e.file.name));
            const deduped = next.filter((e) => !existing.has(e.file.name));
            const combined = [...prev, ...deduped];
            return combined.slice(0, MAX_FILES);
        });
    }

    function removeEntry(name: string) {
        setEntries((prev) => prev.filter((e) => e.file.name !== name));
    }

    function handleDrop(event: React.DragEvent) {
        event.preventDefault();
        setDragOver(false);
        if (event.dataTransfer.files.length > 0) {
            addFiles(event.dataTransfer.files);
        }
    }

    async function handleUpload() {
        const pending = entries.filter((e) => e.status === "pending");
        if (pending.length === 0) return;

        setUploading(true);
        try {
            const result = await onUpload(pending.map((e) => e.file));

            const doneNames = new Set(result.created.map((d) => d.filename));
            const errorMap = new Map(result.errors.map((e) => [e.filename, e.error]));

            setEntries((prev) =>
                prev.map((entry) => {
                    if (doneNames.has(entry.file.name)) {
                        return { ...entry, status: "done" };
                    }
                    const err = errorMap.get(entry.file.name);
                    if (err) {
                        return { ...entry, status: "error", error: err };
                    }
                    return entry;
                })
            );

            onComplete(result);
        } catch (error) {
            const message = (error as Error).message || "Upload failed.";
            const pendingNames = new Set(pending.map((entry) => entry.file.name));
            setEntries((prev) =>
                prev.map((entry) => {
                    if (!pendingNames.has(entry.file.name)) {
                        return entry;
                    }
                    return { ...entry, status: "error", error: message };
                })
            );
        } finally {
            setUploading(false);
        }
    }

    const pendingCount = entries.filter((e) => e.status === "pending").length;
    const doneCount = entries.filter((e) => e.status === "done").length;
    const errorCount = entries.filter((e) => e.status === "error").length;

    return (
        <div className="bulk-upload-panel">
            <div
                className={dragOver ? "drop-zone drop-zone-active" : "drop-zone"}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
                aria-label="Drop files here or click to browse"
            >
                <span className="drop-zone-label">
                    {dragOver
                        ? "Drop to add files"
                        : `Drop PDFs here or click to browse (max ${MAX_FILES})`}
                </span>
                <input
                    ref={inputRef}
                    type="file"
                    multiple
                    accept=".pdf"
                    className="drop-zone-input"
                    onChange={(e) => { if (e.target.files) addFiles(e.target.files); }}
                />
            </div>

            {entries.length > 0 && (
                <>
                    <div className="bulk-file-list">
                        {entries.map((entry) => (
                            <div key={entry.file.name} className={`bulk-file-row bulk-file-${entry.status}`}>
                                <span className="bulk-file-name">{entry.file.name}</span>
                                <span className="bulk-file-size">
                                    {(entry.file.size / 1024).toFixed(0)} KB
                                </span>
                                <span className="bulk-file-status">
                                    {entry.status === "pending" && "Pending"}
                                    {entry.status === "done" && "Done"}
                                    {entry.status === "error" && (entry.error ?? "Error")}
                                </span>
                                {entry.status === "pending" && (
                                    <button
                                        type="button"
                                        className="bulk-file-remove"
                                        onClick={() => removeEntry(entry.file.name)}
                                        aria-label={`Remove ${entry.file.name}`}
                                    >
                                        ×
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>

                    <div className="bulk-upload-footer">
                        <span className="bulk-upload-summary">
                            {pendingCount > 0 && `${pendingCount} pending`}
                            {doneCount > 0 && ` · ${doneCount} uploaded`}
                            {errorCount > 0 && ` · ${errorCount} failed`}
                        </span>
                        <div className="bulk-upload-actions">
                            {pendingCount > 0 && (
                                <Button
                                    variant="primary"
                                    disabled={uploading}
                                    onClick={() => { void handleUpload(); }}
                                >
                                    {uploading ? `Uploading ${pendingCount} files…` : `Upload ${pendingCount} files`}
                                </Button>
                            )}
                            <Button
                                disabled={uploading}
                                onClick={() => setEntries([])}
                            >
                                Clear
                            </Button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
