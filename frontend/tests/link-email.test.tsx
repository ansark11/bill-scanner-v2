/**
 * Phase 1 eval: link-email/page.tsx auto-triggers the initial scan once the
 * Gmail OAuth callback redirects back with ?status=success. It queries
 * gmail_accounts directly via Supabase and silently no-ops if that query is
 * empty or the session is missing — no error path, no user feedback. These
 * tests pin down the (already correct) happy path and the (currently
 * silent) failure paths.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const push = vi.fn();
let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

const getSession = vi.fn();
const fromSelectEqLimit = vi.fn();
vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession },
    from: () => ({
      select: () => ({
        eq: () => ({
          limit: (...args: unknown[]) => fromSelectEqLimit(...args),
        }),
      }),
    }),
  }),
}));

import LinkEmailPage from "@/app/(app)/link-email/page";

beforeEach(() => {
  vi.restoreAllMocks();
  push.mockClear();
  getSession.mockReset();
  fromSelectEqLimit.mockReset();
  searchParams = new URLSearchParams();
});

describe("LinkEmailPage — happy path", () => {
  it("triggers the initial scan and redirects home when a gmail account exists", async () => {
    searchParams.set("status", "success");
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok", user: { id: "user-1" } } },
    });
    fromSelectEqLimit.mockResolvedValue({ data: [{ id: "gmail-acct-1" }] });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({ scan_job_id: "job-1" }) }))
    );

    render(<LinkEmailPage />);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/home"));
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/scan/initial"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("shows an error message when fetching the OAuth auth-url fails", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok", user: { id: "user-1" } } },
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));

    render(<LinkEmailPage />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /connect gmail/i }));

    expect(await screen.findByText(/failed to get auth url/i)).toBeInTheDocument();
  });
});

describe("LinkEmailPage — resilience gaps", () => {
  it("gives the user feedback if no gmail account is found after a successful OAuth redirect", async () => {
    searchParams.set("status", "success");
    getSession.mockResolvedValue({
      data: { session: { access_token: "tok", user: { id: "user-1" } } },
    });
    fromSelectEqLimit.mockResolvedValue({ data: [] });
    vi.stubGlobal("fetch", vi.fn());

    render(<LinkEmailPage />);

    // Current implementation just returns silently here — no redirect, no
    // error, no retry affordance. The user is left on "Starting your
    // initial scan..." indefinitely with nothing actually happening.
    await waitFor(() => expect(fetch).not.toHaveBeenCalled());
    await waitFor(
      () =>
        expect(
          screen.queryByText(/starting your initial scan/i)
        ).not.toBeInTheDocument(),
      { timeout: 2000 }
    );
  });

  it("gives the user feedback if the session is missing when the OAuth redirect lands", async () => {
    searchParams.set("status", "success");
    getSession.mockResolvedValue({ data: { session: null } });
    vi.stubGlobal("fetch", vi.fn());

    render(<LinkEmailPage />);

    await waitFor(
      () =>
        expect(
          screen.queryByText(/starting your initial scan/i)
        ).not.toBeInTheDocument(),
      { timeout: 2000 }
    );
  });
});
