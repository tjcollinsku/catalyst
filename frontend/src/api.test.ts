import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { createCase, fetchCases } from "./api";

describe("api client", () => {
    const fetchMock = vi.fn<typeof fetch>();

    beforeEach(() => {
        vi.stubGlobal("fetch", fetchMock);
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
        vi.useRealTimers();
    });

    test("sends JSON body and headers when creating a case", async () => {
        fetchMock.mockResolvedValue(
            new Response(
                JSON.stringify({
                    id: "case-1",
                    name: "Test Case",
                    status: "OPEN",
                    notes: "",
                    referral_ref: "REF-1",
                    created_at: "2026-03-29T00:00:00Z",
                    updated_at: "2026-03-29T00:00:00Z"
                }),
                {
                    status: 201,
                    headers: { "Content-Type": "application/json" }
                }
            )
        );

        await createCase({ name: "Test Case", referral_ref: "REF-1" });

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock).toHaveBeenCalledWith(
            "/api/cases/",
            expect.objectContaining({
                method: "POST",
                body: JSON.stringify({ name: "Test Case", referral_ref: "REF-1" }),
                signal: expect.any(AbortSignal)
            })
        );

        const init = fetchMock.mock.calls[0][1] as RequestInit;
        const headers = new Headers(init.headers);
        expect(headers.get("Content-Type")).toBe("application/json");
        expect(headers.get("Accept")).toBe("application/json");
    });

    test("formats structured API errors into readable messages", async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ detail: "Access denied" }), {
                status: 403,
                headers: { "Content-Type": "application/json" }
            })
        );

        await expect(fetchCases()).rejects.toThrow("Request failed (403): Access denied");
    });

    test("times out slow requests with a clear message", async () => {
        vi.useFakeTimers();
        fetchMock.mockImplementation(
            (_input, init) => new Promise((_resolve, reject) => {
                const signal = init?.signal as AbortSignal | undefined;
                signal?.addEventListener("abort", () => {
                    reject(new DOMException("The operation was aborted.", "AbortError"));
                });
            }) as Promise<Response>
        );

        const requestPromise = fetchCases(25, 0, { timeoutMs: 25 });
        const assertion = expect(requestPromise).rejects.toThrow("Request timed out after 25ms.");
        await vi.advanceTimersByTimeAsync(25);

        await assertion;
    });
});
