"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

interface Bill {
  id: string;
  biller_name: string;
  biller_account_number: string | null;
  amount_due: number | null;
  currency: string;
  due_date: string | null;
}

interface ScanJob {
  id: string;
  status: "running" | "completed" | "failed";
  error?: string;
}

type HomeState =
  | "loading"
  | "no-gmail"
  | "scanning"
  | "scan-failed"
  | "ready";

function daysUntil(dateStr: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dateStr);
  return Math.round((due.getTime() - today.getTime()) / 86400000);
}

export default function HomePage() {
  const router = useRouter();
  const supabase = createClient();
  const [state, setState] = useState<HomeState>("loading");
  const [bills, setBills] = useState<Bill[]>([]);
  const [scanJob, setScanJob] = useState<ScanJob | null>(null);
  const [gmailAccountId, setGmailAccountId] = useState<string | null>(null);
  const [hasConfirmedBillers, setHasConfirmedBillers] = useState(false);
  const [newBillersFound, setNewBillersFound] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    init();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  async function getSession() {
    const { data: { session } } = await supabase.auth.getSession();
    return session;
  }

  async function init() {
    const session = await getSession();
    if (!session) { router.push("/login"); return; }

    // Check for linked Gmail account
    const { data: accounts } = await supabase
      .from("gmail_accounts")
      .select("id")
      .eq("user_id", session.user.id)
      .limit(1);

    if (!accounts || accounts.length === 0) {
      setState("no-gmail");
      return;
    }
    setGmailAccountId(accounts[0].id);

    // Check for running scan job
    const { data: runningJobs } = await supabase
      .from("scan_jobs")
      .select("id, status")
      .eq("user_id", session.user.id)
      .eq("status", "running")
      .order("started_at", { ascending: false })
      .limit(1);

    if (runningJobs && runningJobs.length > 0) {
      setScanJob(runningJobs[0]);
      setState("scanning");
      startPolling(runningJobs[0].id);
      return;
    }

    // Check for failed scan
    const { data: failedJobs } = await supabase
      .from("scan_jobs")
      .select("id, status, error")
      .eq("user_id", session.user.id)
      .eq("status", "failed")
      .order("started_at", { ascending: false })
      .limit(1);

    // Check if ANY scan has completed successfully
    const { data: completedJobs } = await supabase
      .from("scan_jobs")
      .select("id")
      .eq("user_id", session.user.id)
      .eq("status", "completed")
      .limit(1);

    if (failedJobs && failedJobs.length > 0 && (!completedJobs || completedJobs.length === 0)) {
      setScanJob(failedJobs[0]);
      setState("scan-failed");
      return;
    }

    // No scan jobs at all — trigger initial scan
    const { data: allJobs } = await supabase
      .from("scan_jobs")
      .select("id")
      .eq("user_id", session.user.id)
      .limit(1);

    if (!allJobs || allJobs.length === 0) {
      const gmailId = accounts[0].id;
      const res = await fetch(`${BACKEND_URL}/scan/initial`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ gmail_account_id: gmailId }),
      });
      if (res.ok) {
        const { scan_job_id } = await res.json();
        setScanJob({ id: scan_job_id, status: "running" });
        setState("scanning");
        startPolling(scan_job_id);
      }
      return;
    }

    // Check for pending bills (first-time scan not yet reviewed)
    const { data: pendingBills } = await supabase
      .from("bills")
      .select("id")
      .eq("user_id", session.user.id)
      .eq("status", "pending")
      .limit(1);

    if (pendingBills && pendingBills.length > 0) {
      router.push("/scan-results");
      return;
    }

    await loadDashboard(session.access_token, session.user.id);
  }

  async function loadDashboard(accessToken: string, userId: string) {
    const res = await fetch(`${BACKEND_URL}/bills/current-month`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const data: Bill[] = await res.json();
    setBills(data);

    // Check if any confirmed billers exist
    const { data: billers } = await supabase
      .from("billers")
      .select("id, created_at")
      .eq("user_id", userId);
    setHasConfirmedBillers((billers?.length ?? 0) > 0);

    // New billers banner
    const lastViewed = localStorage.getItem("last_new_billers_viewed_at");
    if (lastViewed && billers) {
      const newBillers = billers.filter(
        (b) => new Date(b.created_at) > new Date(lastViewed)
      );
      setNewBillersFound(newBillers.length > 0);
    }

    setState("ready");
  }

  function startPolling(jobId: string) {
    pollRef.current = setInterval(async () => {
      const session = await getSession();
      if (!session) return;
      const res = await fetch(`${BACKEND_URL}/scan/status/${jobId}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const job: ScanJob = await res.json();
      setScanJob(job);
      if (job.status === "completed") {
        clearInterval(pollRef.current!);
        // After scan completes, redirect to review
        router.push("/scan-results");
      } else if (job.status === "failed") {
        clearInterval(pollRef.current!);
        setState("scan-failed");
      }
    }, 3000);
  }

  async function handleRetry() {
    const session = await getSession();
    if (!session || !gmailAccountId) return;
    const res = await fetch(`${BACKEND_URL}/scan/initial`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ gmail_account_id: gmailAccountId }),
    });
    const { scan_job_id } = await res.json();
    setScanJob({ id: scan_job_id, status: "running" });
    setState("scanning");
    startPolling(scan_job_id);
  }

  if (state === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </main>
    );
  }

  if (state === "no-gmail") {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-sm text-center">
          <CardHeader>
            <CardTitle>Connect your Gmail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Link your Gmail account to start tracking bills.
            </p>
            <Link href="/link-email" className={cn(buttonVariants(), "w-full text-center")}>
              Connect Gmail
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (state === "scanning") {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-sm text-center">
          <CardHeader>
            <CardTitle>Scanning your inbox...</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              We&apos;re looking through 180 days of emails. This may take a minute.
            </p>
            <div className="mt-4 h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
            </div>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (state === "scan-failed") {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-sm text-center">
          <CardHeader>
            <CardTitle>Scan failed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {scanJob?.error || "Something went wrong. Please try again."}
            </p>
            <Button onClick={handleRetry} className="w-full">
              Retry scan
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  // Ready state
  const today = new Date();
  const monthName = today.toLocaleString("default", { month: "long" });

  return (
    <main className="max-w-lg mx-auto p-4 py-8 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Bills due in {monthName}</h1>
        {hasConfirmedBillers && (
          <Link href="/billers" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
            All billers
          </Link>
        )}
      </div>

      {newBillersFound && (
        <Card className="border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-800">
          <CardContent className="flex items-center justify-between pt-4 pb-4">
            <p className="text-sm font-medium">New billers found</p>
            <Link href="/new-billers" className={cn(buttonVariants({ size: "sm", variant: "outline" }))}>
              Review
            </Link>
          </CardContent>
        </Card>
      )}

      {bills.length === 0 ? (
        <Card>
          <CardContent className="pt-6 pb-6 text-center text-muted-foreground">
            No bills due this month.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {bills.map((bill) => {
            const days = bill.due_date ? daysUntil(bill.due_date) : null;
            return (
              <Card key={bill.id}>
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{bill.biller_name}</p>
                      {bill.biller_account_number && (
                        <p className="text-xs text-muted-foreground">
                          {bill.biller_account_number}
                        </p>
                      )}
                      {bill.due_date && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Due {new Date(bill.due_date + "T00:00:00").toLocaleDateString()}
                          {days !== null && (
                            <span className="ml-1">
                              ({days === 0 ? "today" : days < 0 ? `${Math.abs(days)}d overdue` : `${days}d`})
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      {bill.amount_due !== null ? (
                        <p className="font-semibold">
                          {bill.currency} {bill.amount_due.toFixed(2)}
                        </p>
                      ) : (
                        <Badge variant="secondary">Amount unknown</Badge>
                      )}
                      {days !== null && days <= 3 && days >= 0 && (
                        <Badge variant="destructive" className="mt-1 text-xs">
                          Due soon
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </main>
  );
}
