import { Component, ErrorInfo, ReactNode } from "react";
import styles from "./ErrorBoundary.module.css";

interface ErrorBoundaryProps {
    children: ReactNode;
    fallbackTitle?: string;
}

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
}

/**
 * React error boundary — catches rendering errors in child trees
 * and shows a friendly fallback instead of a blank screen.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("[ErrorBoundary]", error, info.componentStack);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className={styles.root} role="alert">
                    <span className={styles.icon}>{"\u26A0\uFE0F"}</span>
                    <h2>{this.props.fallbackTitle ?? "Something went wrong"}</h2>
                    <p>
                        An unexpected error occurred while rendering this view.
                        Try refreshing the page or navigating to a different section.
                    </p>
                    {this.state.error && (
                        <pre>{this.state.error.message}</pre>
                    )}
                    <button
                        className="btn-primary"
                        onClick={() => this.setState({ hasError: false, error: null })}
                        style={{ marginTop: "0.75rem" }}
                    >
                        Try Again
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}
