import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A native select with its own chevron. The browser's arrow sits against the
 * right border whatever the padding says, so it is hidden and drawn here with
 * room either side.
 */
export function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <span className="relative inline-flex">
      <select {...props} className={cn("appearance-none", className, "pr-7")}>
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
    </span>
  );
}
