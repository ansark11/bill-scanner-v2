"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

interface Bill {
  id: string;
  biller_id: string;
  biller_name: string;
  biller_account_number: string | null;
}

export default function NewBillersPage() {
  const router = useRouter();
  const supabase = createClient();
  const [grouped, setGrouped] = useState<Record<string, Bill[]>>({});
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // Update the last-viewed timestamp
    localStorage.setItem("last_new_billers_viewed_at", new Date().toISOString());
    fetchNewBillers();
  }, []);

  async function fetchNewBillers() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;

    const res = await fetch(`${BACKEND_URL}/bills/pending`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    const data: Bill[] = await res.json();

    // Filter to only bills created after the previous last_viewed value
    // (we just reset it above so use the in-memory previous value, or just show all pending)
    const groups: Record<string, Bill[]> = {};
    data.forEach((b) => {
      if (!groups[b.biller_id]) groups[b.biller_id] = [];
      groups[b.biller_id].push(b);
    });
    setGrouped(groups);

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

    Object.entries(grouped).forEach(([billerId, bills]) => {
      bills.forEach((b) => {
        if (checked[billerId]) confirmed_bill_ids.push(b.id);
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
        <p className="text-muted-foreground">Loading...</p>
      </main>
    );
  }

  const billerIds = Object.keys(grouped);

  return (
    <main className="max-w-lg mx-auto p-4 py-8 space-y-4">
      <div>
        <h1 className="text-2xl font-bold">New billers found</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Review billers found in the latest scan.
        </p>
      </div>

      {billerIds.length === 0 ? (
        <Card>
          <CardContent className="pt-6 pb-6 text-center text-muted-foreground">
            No new billers to review.
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
                      {rep.biller_name || billerId}
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
