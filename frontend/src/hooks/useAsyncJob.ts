import { useCallback, useEffect, useRef, useState } from "react";
import type { JobEnqueueResponse, JobStatus, SearchJobSummary } from "../types";

const POLL_INTERVAL_MS = 2000;

export type UseAsyncJobStatus = "idle" | "queued" | "running" | "success" | "failed";

export interface UseAsyncJobReturn<TResult> {
    status: UseAsyncJobStatus;
    jobId: string | null;
    result: TResult | null;
    error: string | null;
    run: (body: Record<string, unknown>) => Promise<void>;
    reattach: (jobId: string) => void;
    cancel: () => void;
}

export interface UseAsyncJobOptions {
    postUrl: string;
}

function getCSRFToken(): string {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
}

async function pollJob(jobId: string): Promise<SearchJobSummary> {
    const res = await fetch(`/api/jobs/${jobId}/`, {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
    });
    if (!res.ok) {
        throw new Error(`Poll failed: ${res.status}`);
    }
    return res.json() as Promise<SearchJobSummary>;
}

export function useAsyncJob<TResult = unknown>(
    options: UseAsyncJobOptions,
): UseAsyncJobReturn<TResult> {
    const [status, setStatus] = useState<UseAsyncJobStatus>("idle");
    const [jobId, setJobId] = useState<string | null>(null);
    const [result, setResult] = useState<TResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
    const mounted = useRef(true);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            if (pollTimer.current !== null) {
                clearInterval(pollTimer.current);
                pollTimer.current = null;
            }
        };
    }, []);

    const stopPolling = useCallback(() => {
        if (pollTimer.current !== null) {
            clearInterval(pollTimer.current);
            pollTimer.current = null;
        }
    }, []);

    const applyJobState = useCallback(
        (job: SearchJobSummary) => {
            if (!mounted.current) return;
            const jobStatus = job.status as JobStatus;
            if (jobStatus === "QUEUED") {
                setStatus("queued");
            } else if (jobStatus === "RUNNING") {
                setStatus("running");
            } else if (jobStatus === "SUCCESS") {
                setStatus("success");
                setResult(job.result as TResult);
                stopPolling();
            } else if (jobStatus === "FAILED") {
                setStatus("failed");
                setError(job.error_message || "Job failed");
                stopPolling();
            }
        },
        [stopPolling],
    );

    const startPolling = useCallback(
        (id: string) => {
            stopPolling();
            const tick = async () => {
                try {
                    const job = await pollJob(id);
                    applyJobState(job);
                } catch (e) {
                    if (!mounted.current) return;
                    setStatus("failed");
                    setError(e instanceof Error ? e.message : "Poll failed");
                    stopPolling();
                }
            };
            pollTimer.current = setInterval(tick, POLL_INTERVAL_MS);
        },
        [applyJobState, stopPolling],
    );

    const run = useCallback(
        async (body: Record<string, unknown>) => {
            setStatus("queued");
            setResult(null);
            setError(null);
            try {
                const res = await fetch(options.postUrl, {
                    method: "POST",
                    credentials: "include",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCSRFToken(),
                    },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    throw new Error(`Enqueue failed: ${res.status}`);
                }
                const enqueue = (await res.json()) as JobEnqueueResponse;
                setJobId(enqueue.job_id);
                startPolling(enqueue.job_id);
            } catch (e) {
                setStatus("failed");
                setError(e instanceof Error ? e.message : "Enqueue failed");
            }
        },
        [options.postUrl, startPolling],
    );

    const reattach = useCallback(
        (id: string) => {
            setStatus("queued");
            setResult(null);
            setError(null);
            setJobId(id);
            startPolling(id);
        },
        [startPolling],
    );

    const cancel = useCallback(() => {
        stopPolling();
        setStatus("idle");
    }, [stopPolling]);

    return { status, jobId, result, error, run, reattach, cancel };
}
