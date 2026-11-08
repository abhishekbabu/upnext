import { Check, Undo2 } from "lucide-react";
import { episodeCode } from "@/lib/format";
import { useWatch } from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * Mark an episode watched now, or — with `undo` — take back the last time it
 * was marked here. Only what upnext recorded can be taken back; imported
 * history is the export's.
 */
export function WatchButton({
  episodeId,
  season,
  episode,
  undo = false,
}: {
  episodeId: number;
  season: number;
  episode: number;
  undo?: boolean;
}) {
  const { mark, unmark } = useWatch();
  const mutation = undo ? unmark : mark;
  const code = episodeCode(season, episode);

  return (
    <button
      type="button"
      onClick={(event) => {
        // Rows that hold this button are links; marking must not also navigate.
        event.preventDefault();
        event.stopPropagation();
        mutation.mutate(episodeId);
      }}
      disabled={mutation.isPending}
      aria-label={undo ? `Unmark ${code}` : `Mark ${code} watched`}
      title={undo ? "Unmark" : "Mark watched"}
      className={cn(
        "inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-border transition-colors",
        "text-muted-foreground hover:border-ok hover:text-ok disabled:opacity-50",
      )}
    >
      {undo ? <Undo2 className="size-3.5" aria-hidden /> : <Check className="size-3.5" aria-hidden />}
    </button>
  );
}
