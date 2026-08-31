import { Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * The three things every panel does while it has nothing to show.
 *
 * Waiting should look the same everywhere, because it means the same thing
 * everywhere — and an empty result said in each panel's own words reads as
 * three different problems rather than one ordinary state.
 */

/** A placeholder shaped like the thing that is coming. */
export function Loading({ shape = "rows" }: { shape?: "rows" | "shelf" }) {
  return (
    <div
      className={cn(shape === "shelf" ? "grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-5" : "flex flex-col gap-3")}
      // Announced politely: a screen reader should hear that something is
      // coming, not have the page read out again as rows arrive.
      role="status"
      aria-live="polite"
      aria-label="Loading"
    >
      {Array.from({ length: shape === "shelf" ? 12 : 5 }, (_, i) =>
        shape === "shelf" ? (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="aspect-[2/3] w-full rounded-md" />
            <Skeleton className="h-3.5 w-3/4" />
          </div>
        ) : (
          <Skeleton key={i} className="h-14 w-full" />
        ),
      )}
    </div>
  );
}

/** For work someone started, where a placeholder would look like a mistake. */
export function Working({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-6 text-[13.5px] text-muted-foreground" role="status" aria-live="polite">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

/** Nothing to show, said once and in the same shape every time. */
export function Empty({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 py-14 text-left">
      <p className="font-display text-[17px] font-semibold tracking-tight">{title}</p>
      {detail && <p className="max-w-[60ch] text-[13.5px] leading-relaxed text-muted-foreground">{detail}</p>}
      {action}
    </div>
  );
}

/** A failure, in the server's own words. */
export function Failed({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3.5" role="alert">
      <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-destructive">Error</p>
      <p className="mt-1 text-[13.5px] leading-relaxed">{message}</p>
    </div>
  );
}
