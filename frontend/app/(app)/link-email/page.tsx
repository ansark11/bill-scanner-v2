"use client";

import { useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

function LinkEmailContent() {
  const params = useSearchParams();
  const router = useRouter();
  const status = params.get("status");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const supabase = createClient();

  useEffect(() => {
    if (status === "success") {
      triggerInitialScan();
    }
  }, [status]);

  async function triggerInitialScan() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      setError("You've been signed out. Please log in again.");
      return;
    }

    const { data: accounts } = await supabase
      .from("gmail_accounts")
      .select("id")
      .eq("user_id", session.user.id)
      .limit(1);

    if (!accounts || accounts.length === 0) {
      setError("We couldn't find your connected Gmail account. Please try connecting again.");
      return;
    }
    const gmailAccountId = accounts[0].id;

    await fetch(`${BACKEND_URL}/scan/initial`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ gmail_account_id: gmailAccountId }),
    });

    router.push("/home");
  }

  async function handleConnect() {
    setLoading(true);
    setError("");
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setError("Not authenticated"); setLoading(false); return; }

    const res = await fetch(`${BACKEND_URL}/gmail/auth-url`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });

    if (!res.ok) {
      setError("Failed to get auth URL");
      setLoading(false);
      return;
    }

    const { auth_url } = await res.json();
    window.location.href = auth_url;
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm text-center">
        <CardHeader>
          <CardTitle className="text-2xl">Connect Gmail</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {status === "success" && !error ? (
            <p className="text-sm text-green-600">
              Gmail connected successfully! Starting your initial scan...
            </p>
          ) : !error && (
            <p className="text-sm text-muted-foreground">
              Bill Wrangler needs read-only access to your Gmail to find bill emails.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button onClick={handleConnect} disabled={loading} className="w-full">
            {loading ? "Redirecting..." : "Connect Gmail"}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}

export default function LinkEmailPage() {
  return (
    <Suspense>
      <LinkEmailContent />
    </Suspense>
  );
}
