import { useState } from "react";
import { cn } from "@/lib/utils";
import { initials, poster, type PosterSize } from "@/lib/format";
import { useConfig } from "@/lib/queries";

/**
 * A title's artwork, or a legible stand-in for it.
 *
 * Two in five of an imported library can arrive without a poster — anything
 * TMDB never matched, plus talk shows and specials it has no artwork for — so
 * the fallback is not an edge case. It shows the title's initials on the same
 * frame at the same aspect ratio, which keeps a shelf a grid rather than a
 * ragged line of different-sized holes.
 */
export function Poster({
  name,
  path,
  size = "w342",
  className,
}: {
  name: string;
  path: string | null;
  size?: PosterSize;
  className?: string;
}) {
  const { data: config, isPending } = useConfig();
  const url = config ? poster(config.image_base, path, size) : null;
  // A path TMDB no longer serves falls back to initials, not a broken image.
  const [failed, setFailed] = useState<string | null>(null);
  const src = url !== failed ? url : null;
  // Until the artwork CDN is known, a poster that has a path is a blank frame
  // rather than initials, which would flash and then be replaced. If it cannot
  // be known, initials.
  const waiting = isPending && path;

  return (
    <div
      className={cn(
        "relative aspect-[2/3] w-full overflow-hidden rounded-md border border-border bg-photo",
        className,
      )}
    >
      {src ? (
        <img
          src={src}
          // The name is already rendered beside every poster this component is
          // used in, so repeating it here would have a screen reader say it
          // twice. Decorative by construction, not by oversight.
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(src)}
          className="size-full object-cover"
        />
      ) : waiting ? null : (
        <div className="flex size-full items-center justify-center bg-secondary p-2">
          <span className="font-display text-2xl font-semibold text-muted-foreground" aria-hidden>
            {initials(name)}
          </span>
        </div>
      )}
    </div>
  );
}
