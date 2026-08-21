/**
 * Phase 1 eval: frontend resilience for the scan-review flow.
 *
 * scan-results/page.tsx never checks `res.ok` before parsing JSON, and its
 * effect returns early (without clearing `loading`) whenever there's no
 * Supabase session. Both are plausible real-world states (an expired
 * session while the tab was idle after a scan; a backend blip) and neither
 * is currently handled, so this file establishes what "handled" should mean
 * and lets these tests fail loudly until it is.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const getSession = vi.fn();
vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({ auth: { getSession } }),
}));

import ScanResultsPage from "@/app/(app)/scan-results/page";

const PENDING_BILLS = [
  {
    id: "bill-1",
    biller_id: "biller-1",
    biller_name: "Acme Power",
    biller_account_number: "ACC-1",
    amount_due: 42.5,
    currency: "CAD",
    due_date: "2026-09-01",
  },
  {
    id: "bill-2",
    biller_id: "biller-1",
    biller_name: "Acme Power",
    biller_account_number: "ACC-1",
    amount_due: 10,
    currency: "CAD",
    due_date: "2026-09-05",
  },
  {
    id: "bill-3",
    biller_id: "biller-2",
    biller_name: "Beta Telecom",
    biller_account_number: "ACC-2",
    amount_due: 60,
    currency: "CAD",
    due_date: "2026-09-10",
  },
];

beforeEach(() => {
  vi.restoreAllMocks();
  push.mockClear();
  getSession.mockReset();
});

describe("ScanResultsPage — happy path", () => {
  it("groups pending bills by biller and confirms the checked ones", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.toString().endsWith("/bills/pending")) {
          return { ok: true, json: async () => PENDING_BILLS } as Response;
        }
        if (url.toString().endsWith("/bills/confirm")) {
          return { ok: true, json: async () => ({ ok: true }) } as Response;
        }
        throw new Error(`unexpected fetch to ${url}`);
      })
    );

    render(<ScanResultsPage />);

    await waitFor(() => expect(screen.getByText("Acme Power")).toBeInTheDocument());
    expect(screen.getByText("Beta Telecom")).toBeInTheDocument();
    expect(screen.getByText("2 bills")).toBeInTheDocument();

    const user = userEvent.setup();
    // Uncheck Beta Telecom so its bill should end up ignored, not confirmed.
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    await user.click(checkboxes[1]);

    await user.click(screen.getByRole("button", { name: /confirm selected billers/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/home"));

    const confirmCall = (fetch as any).mock.calls.find((c: any[]) =>
      c[0].toString().endsWith("/bills/confirm")
    );
    const body = JSON.parse(confirmCall[1].body);
    expect(new Set(body.confirmed_bill_ids)).toEqual(new Set(["bill-1", "bill-2"]));
    expect(body.ignored_bill_ids).toEqual(["bill-3"]);
  });

  it("disables the confirm button while a submission is in flight", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    let resolveConfirm: () => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.toString().endsWith("/bills/pending")) {
          return { ok: true, json: async () => PENDING_BILLS } as Response;
        }
        return new Promise((resolve) => {
          resolveConfirm = () => resolve({ ok: true, json: async () => ({ ok: true }) } as Response);
        });
      })
    );

    render(<ScanResultsPage />);
    await waitFor(() => expect(screen.getByText("Acme Power")).toBeInTheDocument());

    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: /confirm selected billers/i });
    await user.click(button);

    await waitFor(() => expect(button).toBeDisabled());
    resolveConfirm();
  });
});

describe("ScanResultsPage — resilience gaps", () => {
  it("does not hang on 'Loading scan results...' forever when there is no session", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    vi.stubGlobal("fetch", vi.fn());

    render(<ScanResultsPage />);

    // Current implementation: fetchPending() returns before setLoading(false)
    // when session is null, so this never resolves — that's the bug.
    await waitFor(
      () => expect(screen.queryByText("Loading scan results...")).not.toBeInTheDocument(),
      { timeout: 2000 }
    );
  });

  it("shows an error instead of crashing when the backend returns a non-OK response", async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error("not json");
        },
      }))
    );

    render(<ScanResultsPage />);

    // Current implementation calls res.json() unconditionally, with no
    // res.ok check and no try/catch — this should surface a visible error
    // state, not an unhandled rejection with the page stuck loading.
    await waitFor(
      () => expect(screen.queryByText("Loading scan results...")).not.toBeInTheDocument(),
      { timeout: 2000 }
    );
    expect(screen.getByText(/couldn.?t load|something went wrong|error/i)).toBeInTheDocument();
  });
});
