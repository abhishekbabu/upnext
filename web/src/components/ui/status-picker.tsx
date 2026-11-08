import { STATUSES, STATUS_LABELS, type Status } from "@/lib/api";
import { useSetStatus } from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * A title's status, changeable in place. What is chosen here is kept over
 * whatever a later re-import of the export says.
 */
export function StatusPicker({ titleId, status }: { titleId: number; status: Status | null }) {
  const setStatus = useSetStatus();

  return (
    <select
      aria-label="Status"
      value={status ?? ""}
      disabled={setStatus.isPending}
      onChange={(event) => setStatus.mutate({ titleId, status: event.target.value as Status })}
      className={cn(
        "rounded-sm border border-border bg-card px-1.5 py-0.5",
        "font-mono text-[10px] font-medium uppercase tracking-[0.08em] disabled:opacity-50",
      )}
    >
      {status === null && (
        <option value="" disabled>
          No status
        </option>
      )}
      {STATUSES.map((value) => (
        <option key={value} value={value}>
          {STATUS_LABELS[value]}
        </option>
      ))}
    </select>
  );
}
