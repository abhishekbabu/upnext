import { cn } from "@/lib/utils";
import { poster, type PosterSize } from "@/lib/format";

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
  base,
  size = "w342",
  className,
}: {
  name: string;
  path: string | null;
  base: string;
  size?: PosterSize;
  className?: string;
}) {
  const src = poster(base, path, size);

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
          className="size-full object-cover"
        />
      ) : (
        <div className="flex size-full items-center justify-center bg-secondary p-2">
          <span className="font-display text-2xl font-semibold text-muted-foreground" aria-hidden>
            {initials(name)}
          </span>
        </div>
      )}
    </div>
  );
}

/** Up to two initials from a title: "The Last of Us" -> "LU". */
function initials(name: string): string {
  const words = name
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .split(" ")
    .filter((word) => word && !STOP_WORDS.has(word.toLowerCase()));
  if (words.length === 0) return name.slice(0, 1).toUpperCase() || "?";
  return words
    .slice(0, 2)
    .map((word) => word[0]!.toUpperCase())
    .join("");
}

// Dropped so "The Office" reads as "O" rather than "TO", which would collide
// with half a shelf.
const STOP_WORDS = new Set(["the", "a", "an", "of", "and"]);
