"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function VerifyOtpContent() {
  const router = useRouter();
  const params = useSearchParams();
  const email = params.get("email") || "";
  const mode = params.get("mode") || "login";

  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resendCountdown, setResendCountdown] = useState(60);
  const [resendLoading, setResendLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const supabase = createClient();

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setResendCountdown((c) => {
        if (c <= 1) {
          clearInterval(intervalRef.current!);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(intervalRef.current!);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token || token.length !== 6) return;
    setLoading(true);
    setError("");

    const { error } = await supabase.auth.verifyOtp({
      email,
      token,
      type: "email",
    });

    if (error) {
      setError("Invalid or expired code. Please try again.");
      setLoading(false);
    } else {
      router.push("/home");
    }
  }

  async function handleResend() {
    setResendLoading(true);
    await supabase.auth.signInWithOtp({ email });
    setResendCountdown(60);
    setResendLoading(false);
    intervalRef.current = setInterval(() => {
      setResendCountdown((c) => {
        if (c <= 1) { clearInterval(intervalRef.current!); return 0; }
        return c - 1;
      });
    }, 1000);
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl">
            {mode === "signup" ? "Verify your email" : "Enter your code"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            We sent a 6-digit code to <strong>{email}</strong>.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="otp">Verification code</Label>
              <Input
                id="otp"
                placeholder="123456"
                maxLength={6}
                value={token}
                onChange={(e) => setToken(e.target.value.replace(/\D/g, ""))}
                inputMode="numeric"
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Verifying..." : "Verify"}
            </Button>
          </form>
          <div className="mt-4 text-center text-sm text-muted-foreground">
            {resendCountdown > 0 ? (
              <span>Resend code in {resendCountdown}s</span>
            ) : (
              <button
                onClick={handleResend}
                disabled={resendLoading}
                className="underline underline-offset-4 cursor-pointer disabled:opacity-50"
              >
                {resendLoading ? "Sending..." : "Resend code"}
              </button>
            )}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

export default function VerifyOtpPage() {
  return (
    <Suspense>
      <VerifyOtpContent />
    </Suspense>
  );
}
