import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Failed } from "@/components/ui/state";
import { useRemoveTitle } from "@/lib/queries";

/**
 * Remove a title nobody has watched, after a second click to confirm.
 *
 * Confirmed in the page rather than with `window.confirm`, which blocks the
 * whole tab. Imports leave a removed title out from then on, so it does not
 * come back with the next re-import.
 */
export function RemoveTitle({ titleId, name }: { titleId: number; name: string }) {
  const [confirming, setConfirming] = useState(false);
  const remove = useRemoveTitle();
  const navigate = useNavigate();
  const button = "rounded-md border border-border px-2.5 py-1 text-[12.5px] transition-colors disabled:opacity-50";

  if (remove.error) return <Failed error={remove.error} />;
  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className={`${button} text-muted-foreground hover:border-destructive hover:text-destructive`}
      >
        Remove from library
      </button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
      <span className="text-muted-foreground">Remove {name}? Re-imports will leave it out.</span>
      <button
        type="button"
        disabled={remove.isPending}
        onClick={() => remove.mutate(titleId, { onSuccess: () => navigate("/library", { replace: true }) })}
        className={`${button} border-destructive text-destructive hover:bg-destructive/10`}
      >
        Remove
      </button>
      <button type="button" onClick={() => setConfirming(false)} className={`${button} hover:bg-secondary`}>
        Cancel
      </button>
    </div>
  );
}
