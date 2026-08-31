import { Fragment, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, ChevronLeft } from "lucide-react";
import { StatusBadge } from "@/components/ui/badge";
import { Poster } from "@/components/ui/poster";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Empty, Failed, Loading } from "@/components/ui/state";
import type { EpisodeRow, UnmatchedViewing } from "@/lib/api";
import { episodeCode, progressOf, shortDate } from "@/lib/format";
import { useConfig, useTitle } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** One title: its artwork and facts, every episode by season, and what TMDB missed. */
export function Title() {
  const { id } = useParams();
  const config = useConfig();
  const { data, isPending, error } = useTitle(Number(id));

  const seasons = useMemo(() => bySeason(data?.episodes ?? []), [data]);

  if (error) return <Failed error={error} />;
  if (isPending || config.isPending) return <Loading />;

  const progress = progressOf(data);
  const specials = data.episodes.filter((episode) => episode.season_number === 0);
  const watchedSpecials = specials.filter((episode) => episode.watch_count > 0).length;

  return (
    <>
      <Link
        to="/library"
        className="mb-5 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="size-4" aria-hidden />
        Library
      </Link>

      <div className="flex flex-col gap-6 sm:flex-row sm:gap-8">
        <div className="w-40 shrink-0">
          <Poster name={data.name} path={data.poster_path} base={config.data?.image_base ?? ""} size="w342" />
        </div>

        <div className="min-w-0 flex-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight">{data.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            {data.year && <span className="font-mono text-[11px] text-muted-foreground">{data.year}</span>}
            {data.air_status && <span className="font-mono text-[11px] text-muted-foreground">{data.air_status}</span>}
            {data.rating !== null && (
              <span className="font-mono text-[11px] text-muted-foreground">{data.rating}/10</span>
            )}
          </div>

          {data.overview && (
            <p className="mt-4 max-w-[70ch] text-[13.5px] leading-relaxed text-muted-foreground">{data.overview}</p>
          )}

          <div className="mt-5 max-w-sm">
            {progress.kind === "measured" && (
              <>
                <ProgressBar value={progress.share} />
                <p className="mt-1.5 font-mono text-[11px] text-muted-foreground">
                  {progress.watched} of {progress.total} episodes
                </p>
              </>
            )}
            {progress.kind === "counted" && (
              <p className="font-mono text-[11px] text-muted-foreground">
                {progress.watched} episodes watched — not enriched yet, so there is nothing to measure against
              </p>
            )}
            {progress.kind === "unmatched" && (
              <p className="font-mono text-[11px] text-muted-foreground">
                {progress.unmatched} episodes watched, none of them on TMDB&rsquo;s {progress.total}-episode list
              </p>
            )}
            {/* Specials are excluded from TMDB's episode count, so they are
                excluded from the figure above too — otherwise a watched special
                reads as 33 of 32. They are still watched, and still listed. */}
            {watchedSpecials > 0 && (
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                plus {watchedSpecials} {watchedSpecials === 1 ? "special" : "specials"}, which TMDB counts separately
              </p>
            )}
          </div>
        </div>
      </div>

      {data.unmatched.length > 0 && <Unmatched viewings={data.unmatched} />}

      <div className="mt-10">
        {seasons.length === 0 ? (
          <Empty
            title="No episode list"
            detail={
              data.enriched_at
                ? "TMDB has no episodes for this title. Everything you watched is still recorded above."
                : "Run `upnext enrich` to fetch this show's episodes from TMDB."
            }
          />
        ) : (
          seasons.map(([season, episodes]) => (
            <Fragment key={season}>
              <h2 className="mb-2 mt-7 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground first:mt-0">
                {season === 0 ? "Specials" : `Season ${season}`}
              </h2>
              <ul className="divide-y divide-border rounded-md border border-border">
                {episodes.map((episode) => (
                  <li
                    key={episode.id}
                    className={cn(
                      "flex items-baseline gap-3 px-3.5 py-2.5",
                      episode.watch_count === 0 && "text-muted-foreground",
                    )}
                  >
                    <span className="w-16 shrink-0 font-mono text-[11px] text-muted-foreground">
                      {episodeCode(episode.season_number, episode.episode_number)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[13.5px]">{episode.name ?? "—"}</span>
                    {episode.air_date && (
                      <span className="hidden shrink-0 font-mono text-[10.5px] text-muted-foreground sm:inline">
                        {shortDate(episode.air_date)}
                      </span>
                    )}
                    <span className="w-14 shrink-0 text-right">
                      {episode.watch_count > 0 && (
                        <span className="inline-flex items-center gap-1 font-mono text-[10.5px] text-ok">
                          <Check className="size-3.5" aria-hidden />
                          {/* A rewatch is a fact worth keeping: the count shows
                              only above one, so an ordinary watch stays a tick. */}
                          {episode.watch_count > 1 ? `×${episode.watch_count}` : ""}
                          <span className="sr-only">
                            watched {episode.watch_count} {episode.watch_count === 1 ? "time" : "times"}
                          </span>
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Fragment>
          ))
        )}
      </div>
    </>
  );
}

/**
 * Viewings TMDB's episode list has no episode for.
 *
 * Its own section rather than rows mixed into the seasons above: these are not
 * episodes of this show as TMDB understands it, and interleaving them would put
 * the export's numbering back inside the catalog's — which is the shape this
 * whole design exists to undo. They are still viewings, and they still happened.
 */
function Unmatched({ viewings }: { viewings: UnmatchedViewing[] }) {
  const total = viewings.reduce((sum, viewing) => sum + viewing.watch_count, 0);

  return (
    <section className="mt-10 rounded-md border border-warn/40 bg-warn/5 p-4">
      <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-warn">Not in TMDB</h2>
      <p className="mt-1.5 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
        {viewings.length} {viewings.length === 1 ? "episode" : "episodes"} you watched
        {total > viewings.length && ` (${total} viewings)`} that TMDB&rsquo;s list does not contain. Your history and
        TMDB divide this show differently — a service that splits a double-length episode in two, or files a sequel
        series as another season, leaves entries here. They are counted as watched everywhere except the progress
        figure, which can only measure against TMDB&rsquo;s list.
      </p>
      {viewings.length <= INLINE_LIMIT ? (
        <Chips viewings={viewings} />
      ) : (
        // A show numbered wholly differently leaves hundreds of these, and an
        // unbroken wall of them buries the episode list underneath. Folded, so
        // the count leads and the detail is one click away rather than gone.
        <details className="mt-3 group">
          <summary className="cursor-pointer text-[13px] text-muted-foreground marker:text-muted-foreground hover:text-foreground">
            Show all {viewings.length}
          </summary>
          <div className="max-h-80 overflow-y-auto">
            <Chips viewings={viewings} />
          </div>
        </details>
      )}
    </section>
  );
}

/** Beyond this many, the list folds. Eight reads at a glance; three hundred does not. */
const INLINE_LIMIT = 24;

function Chips({ viewings }: { viewings: UnmatchedViewing[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-1.5">
      {viewings.map((viewing) => (
        <li
          key={`${viewing.season_number}x${viewing.episode_number}`}
          className="rounded-sm bg-background px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground"
        >
          {episodeCode(viewing.season_number, viewing.episode_number)}
          {viewing.watch_count > 1 && ` ×${viewing.watch_count}`}
          {viewing.last_watched_at && (
            <span className="ml-1.5 text-muted-foreground/70">{shortDate(viewing.last_watched_at)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Episodes grouped into seasons, in order, specials last.
 *
 * Season 0 is specials at every source. It sorts to the end rather than the
 * front, because a list that opens with specials buries the first real episode
 * of the show under them.
 */
function bySeason(episodes: EpisodeRow[]): [number, EpisodeRow[]][] {
  const groups = new Map<number, EpisodeRow[]>();
  for (const episode of episodes) {
    const group = groups.get(episode.season_number);
    if (group) group.push(episode);
    else groups.set(episode.season_number, [episode]);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === 0) return 1;
    if (b === 0) return -1;
    return a - b;
  });
}
