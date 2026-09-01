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
        {byDay(data).map(([day, drops]) => (
          <Fragment key={day}>
            <h3 className="mb-2 mt-6 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground first:mt-0">
              {airingDay(day, utcToday())}
            </h3>
            <ul className="divide-y divide-border rounded-md border border-border">
              {drops.map((drop) => (
                <li key={`${drop.title_id}x${drop.episodes[0].episode_id}`}>
                  <Link
                    to={`/titles/${drop.title_id}`}
                    className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
                  >
                    <Poster
                      name={drop.name}
                      path={drop.poster_path}
                      base={config.data?.image_base ?? ""}
                      size="w154"
                      className="w-9 shrink-0 rounded-sm"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium leading-snug">{drop.name}</span>
                      {subtitleOf(drop) && (
                        <span className="block truncate text-[12px] text-muted-foreground">{subtitleOf(drop)}</span>
                      )}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{codeOf(drop)}</span>
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
 * Everything one show has airing on one day.
 *
 * A whole season landing at once is one event, not eight — listing it as eight
 * rows of the same name buries every other show that week under it. The
 * episodes are kept so the row can still say which they are.
 */
type Drop = {
  title_id: number;
  name: string;
  poster_path: string | null;
  episodes: [AiringItem, ...AiringItem[]];
};

/**
 * Air dates, in the order the server returned them, each with one entry per
 * show rather than one per episode.
 *
 * Both groupings preserve arrival order, which is already the calendar's: the
 * server sorted by date, then name, then episode number.
 */
function byDay(items: AiringItem[]): [string, Drop[]][] {
  const days = new Map<string, Map<number, Drop>>();
  for (const item of items) {
    let shows = days.get(item.air_date);
    if (!shows) days.set(item.air_date, (shows = new Map()));
    const drop = shows.get(item.title_id);
    if (drop) drop.episodes.push(item);
    else
      shows.set(item.title_id, {
        title_id: item.title_id,
        name: item.name,
        poster_path: item.poster_path,
        episodes: [item],
      });
  }
  return [...days.entries()].map(([day, shows]) => [day, [...shows.values()]]);
}

/** "S02E01" for one episode, "S02E01-E06" for a run of them. */
function codeOf(drop: Drop): string {
  const first = drop.episodes[0];
  const last = drop.episodes[drop.episodes.length - 1] ?? first;
  const code = episodeCode(first.season_number, first.episode_number);
  if (drop.episodes.length === 1) return code;
  // Only the episode half repeats: a same-day drop that spanned two seasons
  // would be a catalog error, and reading "S02E01-S02E06" costs more than it
  // guards against.
  return `${code}-E${String(last.episode_number).padStart(2, "0")}`;
}

/** The episode's own name, or how many arrived when there is more than one. */
function subtitleOf(drop: Drop): string {
  if (drop.episodes.length > 1) return `${drop.episodes.length} episodes`;
  return drop.episodes[0].episode_name ?? "";
}
