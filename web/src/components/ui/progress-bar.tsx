import { cn } from "@/lib/utils";

/**
 * How far through a title someone is.
 *
 * Always paired with the counts in text: a bar alone cannot say whether "most
 * of the way" is 40 of 45 or 400 of 450, and it says nothing at all to a
 * screen reader without the role below.
 */
export function ProgressBar({ value, className }: { value: number; className?: string }) {
  const percent = Math.round(value * 100);
  return (
    <div
      className={cn("h-1 w-full overflow-hidden rounded-full bg-accent", className)}
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn("h-full rounded-full transition-[width]", percent === 100 ? "bg-ok" : "bg-primary")}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
