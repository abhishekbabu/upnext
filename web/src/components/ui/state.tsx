import { SHELF_GRID } from "@/components/ui/shelf";
import { Skeleton } from "@/components/ui/skeleton";

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
      className={shape === "shelf" ? SHELF_GRID : "flex flex-col gap-3"}
      role="status"
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

/** Nothing to show, said once and in the same shape every time. */
export function Empty({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex flex-col items-start gap-3 py-14 text-left">
      <p className="font-display text-[17px] font-semibold tracking-tight">{title}</p>
      {detail && <p className="max-w-[60ch] text-[13.5px] leading-relaxed text-muted-foreground">{detail}</p>}
    </div>
  );
}

/** A failure, in the server's own words. */
export function Failed({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3.5" role="alert">
      <p className="eyebrow text-destructive">Error</p>
      <p className="mt-1 text-[13.5px] leading-relaxed">{message}</p>
    </div>
  );
}
