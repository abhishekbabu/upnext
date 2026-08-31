import { cn } from "@/lib/utils";
import { STATUS_LABELS, type Status } from "@/lib/api";

/** A title's status, in the one shape it takes everywhere. */
export function StatusBadge({ status, className }: { status: Status | null; className?: string }) {
  if (!status) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-1.5 py-0.5",
        "font-mono text-[10px] font-medium uppercase tracking-[0.08em]",
        status === "watching" && "bg-primary text-primary-foreground",
        status === "completed" && "bg-ok/15 text-ok",
        status === "watchlist" && "bg-accent text-accent-foreground",
        status === "stopped" && "bg-secondary text-muted-foreground",
        className,
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
