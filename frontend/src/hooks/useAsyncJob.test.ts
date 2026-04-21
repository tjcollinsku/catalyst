import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAsyncJob } from "./useAsyncJob";

const flushTimers = async () => {
    await vi.runAllTimersAsync();
};

describe("useAsyncJob", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal("fetch", vi.fn());
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    function mockPostReturns(jobId: string) {
        (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            ok: true,
            status: 202,
            json: async () => ({ job_id: jobId, status_url: `/api/jobs/${jobId}/` }),
            headers: new Headers({ "content-type": "application/json" }),
        });
    }

    function mockGetReturns(body: Record<string, unknown>, status = 200) {
        (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
            ok: status < 400,
            status,
            json: async () => body,
            headers: new Headers({ "content-type": "application/json" }),
        });
    }

    it("starts idle", () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );
        expect(result.current.status).toBe("idle");
        expect(result.current.result).toBeNull();
        expect(result.current.error).toBeNull();
    });

    it("transitions idle → queued → running → success", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-1");
        mockGetReturns({ id: "job-1", status: "RUNNING", result: null, error_message: "" });
        mockGetReturns({
            id: "job-1",
            status: "SUCCESS",
            result: { count: 2, results: [{}, {}] },
            error_message: "",
        });

        await act(async () => {
            await result.current.run({ query: "do good" });
        });
        expect(result.current.status).toBe("queued");

        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("running"));

        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("success"));
        expect((result.current.result as { count: number }).count).toBe(2);
    });

    it("transitions to failed on FAILED status", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-2");
        mockGetReturns({
            id: "job-2",
            status: "FAILED",
            result: null,
            error_message: "Connector raised",
        });

        await act(async () => {
            await result.current.run({ query: "x" });
        });
        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("failed"));
        expect(result.current.error).toBe("Connector raised");
    });

    it("reattach skips POST and starts polling immediately", async () => {
        const { result } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockGetReturns({
            id: "job-3",
            status: "SUCCESS",
            result: { count: 1 },
            error_message: "",
        });

        await act(async () => {
            result.current.reattach("job-3");
        });
        await act(flushTimers);
        await waitFor(() => expect(result.current.status).toBe("success"));

        const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
        expect(calls.some(([url]) => String(url).includes("/api/jobs/job-3/"))).toBe(true);
        expect(calls.some(([_url, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
    });

    it("clears poll interval on unmount", async () => {
        const { result, unmount } = renderHook(() =>
            useAsyncJob({ postUrl: "/api/cases/abc/research/irs/" }),
        );

        mockPostReturns("job-4");
        mockGetReturns({ id: "job-4", status: "RUNNING", result: null, error_message: "" });

        await act(async () => {
            await result.current.run({ query: "x" });
        });
        await act(flushTimers);

        unmount();

        const callsBefore = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        await act(flushTimers);
        const callsAfter = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.length;
        expect(callsAfter).toBe(callsBefore);
    });
});
