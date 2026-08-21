"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

interface Bill {
  id: string;
  biller_id: string;
  biller_name: string;
  biller_account_number: string | null;
  amount_due: number | null;
  currency: string;
  due_date: string | null;
}

export default function ScanResultsPage() {
  const router = useRouter();
  const [bills, setBills] = useState<Bill[]>([]);
  const [grouped, setGrouped] = useState<Record<string, Bill[]>>({});
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const supabase = createClient();

  useEffect(() => {
    fetchPending();
  }, []);

  async function fetchPending() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      setError("You've been signed out. Please log in again.");
      setLoading(false);
      return;
    }

    let res: Response;
    try {
      res = await fetch(`${BACKEND_URL}/bills/pending`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
    } catch {
      setError("Something went wrong loading your scan results. Please try again.");
      setLoading(false);
      return;
    }

    if (!res.ok) {
      setError("Something went wrong loading your scan results. Please try again.");
      setLoading(false);
      return;
    }

    const data: Bill[] = await res.json();
    setBills(data);

    // Group by biller_id, keep first bill per biller as representative
    const groups: Record<string, Bill[]> = {};
    data.forEach((b) => {
      if (!groups[b.biller_id]) groups[b.biller_id] = [];
      groups[b.biller_id].push(b);
    });
    setGrouped(groups);

    // Pre-check all billers
    const initialChecked: Record<string, boolean> = {};
    Object.keys(groups).forEach((k) => (initialChecked[k] = true));
    setChecked(initialChecked);
    setLoading(false);
  }

  async function handleConfirm() {
    setSubmitting(true);
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;

    const confirmed_bill_ids: string[] = [];
    const ignored_bill_ids: string[] = [];

    Object.entries(grouped).forEach(([billerId, billerBills]) => {
      const isChecked = checked[billerId];
      billerBills.forEach((b) => {
        if (isChecked) confirmed_bill_ids.push(b.id);
        else ignored_bill_ids.push(b.id);
      });
    });

    await fetch(`${BACKEND_URL}/bills/confirm`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ confirmed_bill_ids, ignored_bill_ids }),
    });

    router.push("/home");
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading scan results...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-destructive">{error}</p>
      </main>
    );
  }

  const billerIds = Object.keys(grouped);

  return (
    <main className="max-w-lg mx-auto p-4 space-y-4 py-8">
      <div>
        <h1 className="text-2xl font-bold">Review scanned billers</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Uncheck any billers you don&apos;t want to track.
        </p>
      </div>

      {billerIds.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            No new billers found in your inbox.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {billerIds.map((billerId) => {
            const rep = grouped[billerId][0];
            return (
              <Card key={billerId}>
                <CardContent className="flex items-center gap-3 pt-4 pb-4">
                  <Checkbox
                    checked={checked[billerId] ?? true}
                    onCheckedChange={(v) =>
                      setChecked((prev) => ({ ...prev, [billerId]: !!v }))
                    }
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">
                      {rep.biller_name || rep.biller_id}
                    </p>
                    {rep.biller_account_number && (
                      <p className="text-xs text-muted-foreground">
                        Account: {rep.biller_account_number}
                      </p>
                    )}
                  </div>
                  <Badge variant="secondary">
                    {grouped[billerId].length} bill{grouped[billerId].length !== 1 ? "s" : ""}
                  </Badge>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Button
        onClick={handleConfirm}
        disabled={submitting || billerIds.length === 0}
        className="w-full"
      >
        {submitting ? "Saving..." : "Confirm selected billers"}
      </Button>
    </main>
  );
}
