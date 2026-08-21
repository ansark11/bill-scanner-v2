import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default async function LandingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect("/home");
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">Bill Wrangler</h1>
        <p className="text-muted-foreground text-lg max-w-sm">
          Connect your Gmail and never miss a bill payment again.
        </p>
      </div>
      <div className="flex gap-4">
        <Link href="/login" className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
          Log in
        </Link>
        <Link href="/signup" className={cn(buttonVariants({ size: "lg" }))}>
          Sign up
        </Link>
      </div>
    </main>
  );
}
