import { useCallback, useRef, useState, useEffect } from "react";
import type { AIAskMessage, AIAskResponse, AIConnectionsResponse, AINarrativeResponse } from "../../types";
import { aiAsk, aiConnections, aiNarrative } from "../../api";
import styles from "./AIAssistantPanel.module.css";

/* ── Types ────────────────────────────────────────────────── */

interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: AIAskResponse["sources"];
    followUps?: string[];
    timestamp: number;
}

interface AIAssistantPanelProps {
    caseId: string;
    caseName?: string;
    open: boolean;
    onClose: () => void;
}

/* ── Quick actions ────────────────────────────────────────── */

const QUICK_ACTIONS = [
    { id: "summarize-case", label: "Summarize case", question: "Give me a concise summary of the entire case, including key entities, red flags, and current status." },
    { id: "key-risks", label: "Key risks", question: "What are the most significant risk indicators and red flags in this case?" },
    { id: "connections", label: "Find connections", action: "connections" as const },
    { id: "timeline", label: "Build timeline", question: "Construct a chronological timeline of the most important events in this case." },
    { id: "next-steps", label: "Suggest next steps", question: "Based on the current evidence, what investigative steps should be taken next?" },
    { id: "draft-narrative", label: "Draft narrative", action: "narrative" as const },
] as const;

let _msgId = 0;
function nextId() { return `msg-${++_msgId}-${Date.now()}`; }

/* ── Component ────────────────────────────────────────────── */

export function AIAssistantPanel({ caseId, caseName, open, onClose }: AIAssistantPanelProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Auto-scroll on new messages
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    // Focus input when panel opens
    useEffect(() => {
        if (open && inputRef.current) {
            setTimeout(() => inputRef.current?.focus(), 200);
        }
    }, [open]);

    // Close on Escape key
    useEffect(() => {
        if (!open) return;
        function onKeyDown(e: KeyboardEvent) {
            if (e.key === "Escape") onClose();
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [open, onClose]);

    /* ── Ask endpoint (free-text chat) ───────────────────── */
    const sendMessage = useCallback(async (question: string) => {
        if (!question.trim() || loading) return;

        const userMsg: ChatMessage = {
            id: nextId(),
            role: "user",
            content: question.trim(),
            timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setInput("");
        setLoading(true);

        try {
            // Build conversation history from last messages
            const history: AIAskMessage[] = messages.slice(-6).map((m) => ({
                role: m.role,
                content: m.content,
            }));

            const result = await aiAsk(caseId, question.trim(), history);
            const assistantMsg: ChatMessage = {
                id: nextId(),
                role: "assistant",
                content: result.answer,
                sources: result.sources,
                followUps: result.follow_up_questions,
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, assistantMsg]);
        } catch (err) {
            const errorMsg: ChatMessage = {
                id: nextId(),
                role: "assistant",
                content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : "Unknown error"}. Please try again.`,
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, errorMsg]);
        } finally {
            setLoading(false);
        }
    }, [caseId, messages, loading]);

    /* ── Connections quick action ─────────────────────────── */
    const runConnections = useCallback(async () => {
        const userMsg: ChatMessage = {
            id: nextId(),
            role: "user",
            content: "Find hidden connections between entities",
            timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setLoading(true);

        try {
            const result: AIConnectionsResponse = await aiConnections(caseId);
            const lines = result.suggestions.map(
                (s) => `**${s.source_label}** \u2192 **${s.target_label}**: ${s.relationship} (${Math.round(s.confidence * 100)}% confidence)\n  _Evidence: ${s.evidence}_`
            );
            const content = result.suggestions.length > 0
                ? `I found ${result.suggestions.length} potential connection(s):\n\n${lines.join("\n\n")}\n\n**Reasoning:** ${result.reasoning}`
                : `No additional hidden connections found beyond what's already mapped. ${result.reasoning}`;

            setMessages((prev) => [...prev, {
                id: nextId(),
                role: "assistant",
                content,
                timestamp: Date.now(),
            }]);
        } catch (err) {
            setMessages((prev) => [...prev, {
                id: nextId(),
                role: "assistant",
                content: `Connection analysis failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                timestamp: Date.now(),
            }]);
        } finally {
            setLoading(false);
        }
    }, [caseId]);

    /* ── Narrative quick action ───────────────────────────── */
    const runNarrative = useCallback(async () => {
        const userMsg: ChatMessage = {
            id: nextId(),
            role: "user",
            content: "Draft an investigative narrative from detections",
            timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setLoading(true);

        try {
            // Pass empty array — the backend will use all confirmed detections
            const result: AINarrativeResponse = await aiNarrative(caseId, [], "formal");
            const legalSection = result.legal_references.length > 0
                ? `\n\n**Legal References:** ${result.legal_references.join(", ")}`
                : "";
            const actionsSection = result.recommended_actions.length > 0
                ? `\n\n**Recommended Actions:**\n${result.recommended_actions.map((a) => `- ${a}`).join("\n")}`
                : "";
            const content = `**${result.title}**\n\n${result.narrative}${legalSection}${actionsSection}`;

            setMessages((prev) => [...prev, {
                id: nextId(),
                role: "assistant",
                content,
                timestamp: Date.now(),
            }]);
        } catch (err) {
            setMessages((prev) => [...prev, {
                id: nextId(),
                role: "assistant",
                content: `Narrative generation failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                timestamp: Date.now(),
            }]);
        } finally {
            setLoading(false);
        }
    }, [caseId]);

    /* ── Quick action handler ────────────────────────────── */
    const handleQuickAction = useCallback((action: typeof QUICK_ACTIONS[number]) => {
        if ("action" in action && action.action === "connections") {
            runConnections();
        } else if ("action" in action && action.action === "narrative") {
            runNarrative();
        } else if ("question" in action) {
            sendMessage(action.question);
        }
    }, [runConnections, runNarrative, sendMessage]);

    /* ── Input submit ────────────────────────────────────── */
    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        sendMessage(input);
    }, [input, sendMessage]);

    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input);
        }
    }, [input, sendMessage]);

    if (!open) return null;

    return (
        <div className={styles.panel} role="complementary" aria-label="AI Assistant panel">
            {/* ── Header ──────────────────────────────────────── */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <span className={styles.aiIcon}>✦</span>
                    <div>
                        <h3 className={styles.title}>AI Assistant</h3>
                        {caseName && <span className={styles.caseName}>{caseName}</span>}
                    </div>
                </div>
                <button className={styles.closeBtn} onClick={onClose} title="Close AI panel">
                    ✕
                </button>
            </div>

            {/* ── Messages ────────────────────────────────────── */}
            <div className={styles.messages} ref={scrollRef}>
                {messages.length === 0 && (
                    <div className={styles.emptyState}>
                        <span className={styles.emptyIcon}>✦</span>
                        <p className={styles.emptyTitle}>Case Intelligence Assistant</p>
                        <p className={styles.emptySubtitle}>
                            Ask questions about this case or use the quick actions below to get started.
                        </p>
                    </div>
                )}

                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`${styles.message} ${msg.role === "user" ? styles.messageUser : styles.messageAssistant}`}
                    >
                        {msg.role === "assistant" && (
                            <span className={styles.msgIcon}>✦</span>
                        )}
                        <div className={styles.msgContent}>
                            <div className={styles.msgText}>{msg.content}</div>
                            {/* Sources */}
                            {msg.sources && msg.sources.length > 0 && (
                                <div className={styles.sources}>
                                    <span className={styles.sourcesLabel}>Sources:</span>
                                    {msg.sources.map((s, i) => (
                                        <span key={i} className={styles.sourceChip}>
                                            {s.type}: {s.label}
                                        </span>
                                    ))}
                                </div>
                            )}
                            {/* Follow-up suggestions */}
                            {msg.followUps && msg.followUps.length > 0 && (
                                <div className={styles.followUps}>
                                    {msg.followUps.map((q, i) => (
                                        <button
                                            key={i}
                                            className={styles.followUpBtn}
                                            onClick={() => sendMessage(q)}
                                            disabled={loading}
                                        >
                                            {q}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                ))}

                {loading && (
                    <div className={`${styles.message} ${styles.messageAssistant}`}>
                        <span className={styles.msgIcon}>✦</span>
                        <div className={styles.msgContent}>
                            <div className={styles.thinkingDots}>
                                <span /><span /><span />
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* ── Quick actions ────────────────────────────────── */}
            {messages.length === 0 && (
                <div className={styles.quickActions}>
                    {QUICK_ACTIONS.map((action) => (
                        <button
                            key={action.id}
                            className={styles.quickActionBtn}
                            onClick={() => handleQuickAction(action)}
                            disabled={loading}
                        >
                            {action.label}
                        </button>
                    ))}
                </div>
            )}

            {/* ── Input ───────────────────────────────────────── */}
            <form className={styles.inputArea} onSubmit={handleSubmit}>
                <textarea
                    ref={inputRef}
                    className={styles.inputField}
                    placeholder="Ask about this case…"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    disabled={loading}
                />
                <button
                    type="submit"
                    className={styles.sendBtn}
                    disabled={loading || !input.trim()}
                    title="Send message"
                >
                    ↑
                </button>
            </form>
        </div>
    );
}
