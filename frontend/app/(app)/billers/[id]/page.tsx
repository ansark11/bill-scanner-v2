"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

interface Biller {
  id: string;
  name: string;
  account_number: string | null;
  sender_email: string | null;
  created_at: string;
}

export default function BillerDetailPage() {
  const router = useRouter();
  const params = useParams();
  const billerId = params.id as string;
  const supabase = createClient();

  const [biller, setBiller] = useState<Biller | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => { fetchBiller(); }, []);

  async function fetchBiller() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    const res = await fetch(`${BACKEND_URL}/bills/billers/${billerId}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    if (!res.ok) { router.push("/billers"); return; }
    setBiller(await res.json());
    setLoading(false);
  }

  async function handleDelete() {
    setDeleting(true);
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await fetch(`${BACKEND_URL}/bills/billers/${billerId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    router.push("/billers");
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </main>
    );
  }

  if (!biller) return null;

  return (
    <main className="max-w-lg mx-auto p-4 py-8 space-y-4">
      <button
        onClick={() => router.back()}
        className="text-sm text-muted-foreground underline underline-offset-4"
      >
        ← Back to billers
      </button>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{biller.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {biller.account_number && (
            <div>
              <span className="text-muted-foreground">Account number: </span>
              <span>{biller.account_number}</span>
            </div>
          )}
          {biller.sender_email && (
            <div>
              <span className="text-muted-foreground">Sender email: </span>
              <span>{biller.sender_email}</span>
            </div>
          )}
          <div>
            <span className="text-muted-foreground">Added: </span>
            <span>{new Date(biller.created_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger render={<Button variant="destructive" className="w-full" />}>
          Delete biller
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {biller.name}?</DialogTitle>
            <DialogDescription>
              This will permanently delete this biller and all associated bill records. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
