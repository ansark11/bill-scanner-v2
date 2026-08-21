"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

interface Biller {
  id: string;
  name: string;
  account_number: string | null;
}

function BillerRow({ biller, onDelete }: { biller: Biller; onDelete: (id: string) => void }) {
  const router = useRouter();
  const [translateX, setTranslateX] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const startX = useRef(0);
  const isDragging = useRef(false);
  const DELETE_THRESHOLD = -80;

  function onTouchStart(e: React.TouchEvent) {
    startX.current = e.touches[0].clientX;
    isDragging.current = true;
  }

  function onTouchMove(e: React.TouchEvent) {
    if (!isDragging.current) return;
    const dx = e.touches[0].clientX - startX.current;
    setTranslateX(Math.min(0, Math.max(-120, dx)));
  }

  function onTouchEnd() {
    isDragging.current = false;
    if (translateX < DELETE_THRESHOLD) {
      setTranslateX(-100);
    } else {
      setTranslateX(0);
    }
  }

  function handleTap() {
    if (Math.abs(translateX) < 10) {
      router.push(`/billers/${biller.id}`);
    } else {
      setTranslateX(0);
    }
  }

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* Delete button revealed behind */}
      <div className="absolute inset-y-0 right-0 flex items-center bg-destructive rounded-r-lg">
        <Button
          variant="destructive"
          size="sm"
          className="h-full rounded-none rounded-r-lg px-5"
          disabled={deleting}
          onClick={() => onDelete(biller.id)}
        >
          Delete
        </Button>
      </div>

      {/* Swipeable card */}
      <Card
        style={{ transform: `translateX(${translateX}px)`, transition: isDragging.current ? "none" : "transform 0.2s ease" }}
        className="cursor-pointer relative bg-background"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={handleTap}
      >
        <CardContent className="flex items-center justify-between py-4 px-4">
          <div>
            <p className="font-medium">{biller.name}</p>
            {biller.account_number && (
              <p className="text-xs text-muted-foreground">
                Account: {biller.account_number}
              </p>
            )}
          </div>
          <span className="text-muted-foreground text-sm">›</span>
        </CardContent>
      </Card>
    </div>
  );
}

export default function BillersPage() {
  const supabase = createClient();
  const [billers, setBillers] = useState<Biller[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { fetchBillers(); }, []);

  async function fetchBillers() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    const res = await fetch(`${BACKEND_URL}/bills/billers`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    const data = await res.json();
    setBillers(data);
    setLoading(false);
  }

  async function handleDelete(billerId: string) {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    await fetch(`${BACKEND_URL}/bills/billers/${billerId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    setBillers((prev) => prev.filter((b) => b.id !== billerId));
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading billers...</p>
      </main>
    );
  }

  return (
    <main className="max-w-lg mx-auto p-4 py-8 space-y-4">
      <h1 className="text-2xl font-bold">All billers</h1>
      <p className="text-xs text-muted-foreground">Swipe left on a biller to delete it.</p>

      {billers.length === 0 ? (
        <Card>
          <CardContent className="pt-6 pb-6 text-center text-muted-foreground">
            No billers yet.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {billers.map((b) => (
            <BillerRow key={b.id} biller={b} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </main>
  );
}
