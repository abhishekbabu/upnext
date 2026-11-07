import { cn } from "@/lib/utils";

/**
 * How far through a title someone is.
 *
 * Always paired with the counts in text: a bar alone cannot say whether "most
 * of the way" is 40 of 45 or 400 of 450, and it says nothing at all to a
 * screen reader without the role below.
 */
export function ProgressBar({ value, label, className }: { value: number; label: string; className?: string }) {
  // Floored, so 227 of 228 never reads as 100.
  const percent = Math.floor(value * 100);
  return (
    <div
      className={cn("h-1 w-full overflow-hidden rounded-full bg-accent", className)}
      role="progressbar"
      aria-label={label}
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn("h-full rounded-full transition-[width]", value >= 1 ? "bg-ok" : "bg-primary")}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
