import { Fragment } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/page-header";
import { Poster } from "@/components/ui/poster";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { airingDay, episodeCode, shortDate } from "@/lib/format";
import { useAiring, useConfig, useUpNext } from "@/lib/queries";
import type { AiringItem } from "@/lib/api";

/**
 * The shelf this app exists for: the next unwatched episode of everything in
 * progress, most recently watched first.
 *
 * "Next" is decided by the server — the lowest-numbered unwatched episode,
 * which is the only definition that survives someone skipping around. Nothing
 * here re-derives it.
 *
 * Below it, the calendar: episodes that have not aired yet. The two are
 * different questions — what to put on now, and what is coming — so they are
 * separate queries and neither is folded into the other.
 */
export function UpNext() {
  const config = useConfig();
  const { data, isPending, error } = useUpNext();

  return (
    <>
      <PageHeader title="Up next" detail="The next episode of everything you have started." />
      {error ? (
        <Failed error={error} />
      ) : isPending || config.isPending ? (
        <Loading shape="shelf" />
      ) : data.length === 0 ? (
        <Empty
          title="Nothing in progress"
          detail="Shows you are part-way through appear here. Import a library and enrich it, then start watching."
        />
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-5 gap-y-7">
          {data.map((item) => (
            <li key={item.episode_id}>
              <Link
                to={`/titles/${item.title_id}`}
                className="group block rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
              >
                <Poster
                  name={item.name}
                  path={item.poster_path}
                  base={config.data?.image_base ?? ""}
                  className="transition-opacity group-hover:opacity-85"
                />
                <p className="mt-2.5 truncate text-[13.5px] font-medium leading-snug" title={item.name}>
                  {item.name}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {episodeCode(item.season_number, item.episode_number)}
                </p>
                {item.episode_name && (
                  <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{item.episode_name}</p>
                )}
                {item.last_watched_at && (
                  <p className="mt-1 font-mono text-[10.5px] text-muted-foreground/80">
                    last watched {shortDate(item.last_watched_at)}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}

      <Airing />
    </>
  );
}

/**
 * Upcoming episodes of shows with watch history, soonest first.
 *
 * Absent rather than empty when there is nothing coming: an "Airing next"
 * heading over a blank space reads as a failure, and having no show with a
 * scheduled episode is an ordinary state — most libraries are mostly finished
 * shows.
 */
function Airing() {
  const config = useConfig();
  const { data, error } = useAiring();

  // A calendar is not what the page is for, so a failure to load one is not
  // worth an error panel over the shelf that did load. The section simply is
  // not there, exactly as when nothing is scheduled.
  if (error || !data || data.length === 0) return null;

  return (
    <section className="mt-12">
      <h2 className="font-display text-lg font-semibold tracking-tight">Airing next</h2>
      <p className="mt-1 text-[13.5px] text-muted-foreground">
        Upcoming episodes of shows you have watched. As current as your last <code className="font-mono">enrich</code>.
      </p>
      <div className="mt-5">
        {byDay(data).map(([day, episodes]) => (
          <Fragment key={day}>
            <h3 className="mb-2 mt-6 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground first:mt-0">
              {airingDay(day, utcToday())}
            </h3>
            <ul className="divide-y divide-border rounded-md border border-border">
              {episodes.map((episode) => (
                <li key={episode.episode_id}>
                  <Link
                    to={`/titles/${episode.title_id}`}
                    className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
                  >
                    <Poster
                      name={episode.name}
                      path={episode.poster_path}
                      base={config.data?.image_base ?? ""}
                      size="w154"
                      className="w-9 shrink-0 rounded-sm"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium leading-snug">{episode.name}</span>
                      {episode.episode_name && (
                        <span className="block truncate text-[12px] text-muted-foreground">
                          {episode.episode_name}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      {episodeCode(episode.season_number, episode.episode_number)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Fragment>
        ))}
      </div>
    </section>
  );
}

/**
 * Today in UTC, as "YYYY-MM-DD".
 *
 * UTC because the server filtered the list on UTC today, and a client labelling
 * against local midnight would call a row "Tomorrow" that the server included
 * as today. An air date carries no timezone of its own, so there is no truer
 * answer to disagree with — only a consistent one.
 */
function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Air dates, in the order the server returned them, each with every episode
 * landing that day.
 *
 * A season dropping at once is listed episode by episode: what is coming is
 * the question, and "six episodes" answers it less completely than naming
 * them. The grouping preserves arrival order, which is already the calendar's
 * — the server sorted by date, then name, then episode number.
 */
function byDay(items: AiringItem[]): [string, AiringItem[]][] {
  const groups = new Map<string, AiringItem[]>();
  for (const item of items) {
    const group = groups.get(item.air_date);
    if (group) group.push(item);
    else groups.set(item.air_date, [item]);
  }
  return [...groups.entries()];
}
