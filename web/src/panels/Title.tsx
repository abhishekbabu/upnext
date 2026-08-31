import { Fragment, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, ChevronLeft } from "lucide-react";
import { StatusBadge } from "@/components/ui/badge";
import { Poster } from "@/components/ui/poster";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Empty, Failed, Loading } from "@/components/ui/state";
import type { EpisodeRow } from "@/lib/api";
import { episodeCode, progress, shortDate } from "@/lib/format";
import { useConfig, useTitle } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** One title: its artwork and facts, then every episode grouped by season. */
export function Title() {
  const { id } = useParams();
  const config = useConfig();
  const { data, isPending, error } = useTitle(Number(id));

  const seasons = useMemo(() => bySeason(data?.episodes ?? []), [data]);

  if (error) return <Failed error={error} />;
  if (isPending || config.isPending) return <Loading />;

  const share = progress(data);

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

          {share !== null && (
            <div className="mt-5 max-w-sm">
              <ProgressBar value={share} />
              <p className="mt-1.5 font-mono text-[11px] text-muted-foreground">
                {data.episodes_watched} of {data.total_episodes} episodes
              </p>
            </div>
          )}
          {share === null && data.episodes_watched > 0 && (
            <p className="mt-5 font-mono text-[11px] text-muted-foreground">
              {data.episodes_watched} episodes watched — no catalog count to measure against yet
            </p>
          )}
        </div>
      </div>

      <div className="mt-10">
        {seasons.length === 0 ? (
          <Empty
            title="No episodes"
            detail="This title has not been enriched, or TMDB has no episode list for it. Its watches are still counted."
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
                          {/* A rewatch is a fact worth keeping: the count is
                              shown only when it is more than one, so an
                              ordinary watch stays a tick. */}
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
