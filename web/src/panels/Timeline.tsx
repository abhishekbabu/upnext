import { Fragment } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/page-header";
import { Poster } from "@/components/ui/poster";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { WatchButton } from "@/components/ui/watch-button";
import { airingDay, episodeCode } from "@/lib/format";
import { useTimeline } from "@/lib/queries";
import { groupBy } from "@/lib/utils";

/**
 * The home page: unwatched episodes of shows you are watching, from the last
 * month through everything scheduled, by air date. Paused (`watch_later`),
 * unstarted, stopped and archived shows stay off it.
 *
 * A list to work down. An episode that is out has a button to mark it, and
 * marking takes it off; what has not aired yet is there to see coming. Older
 * unwatched episodes are the backlog, which is the Up next shelf's question.
 */
export function Timeline() {
  const { data, isPending, error } = useTimeline();

  return (
    <>
      <PageHeader
        title="Timeline"
        detail="Unwatched episodes from the past month, and what is coming, for shows you are watching."
      />
      {error ? (
        <Failed error={error} />
      ) : isPending ? (
        <Loading />
      ) : data.episodes.length === 0 ? (
        <Empty
          title="All caught up"
          detail="Nothing out in the past month is unwatched, and nothing is scheduled. As current as your last `just enrich`."
        />
      ) : (
        // One heading per day, every episode under it: a season dropping at
        // once is listed episode by episode, so each can be marked.
        groupBy(data.episodes, (episode) => episode.air_date).map(([day, episodes]) => (
          <Fragment key={day}>
            <h2 className="eyebrow mb-2 mt-6 first:mt-0">{airingDay(day, data.today)}</h2>
            <ul className="divide-y divide-border rounded-md border border-border">
              {episodes.map((episode) => (
                <li key={episode.episode_id}>
                  <Link
                    to={`/titles/${episode.title_id}`}
                    className="flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-secondary focus-visible:-outline-offset-2"
                  >
                    <Poster name={episode.name} path={episode.poster_path} size="w154" className="w-9 shrink-0 rounded-sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium leading-snug">{episode.name}</span>
                      {episode.episode_name && (
                        <span className="block truncate text-[12px] text-muted-foreground">{episode.episode_name}</span>
                      )}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      {episodeCode(episode.season_number, episode.episode_number)}
                    </span>
                    {/* Air dates compare as text; only what is out can be watched. */}
                    {episode.air_date <= data.today ? (
                      <WatchButton
                        episodeId={episode.episode_id}
                        season={episode.season_number}
                        episode={episode.episode_number}
                      />
                    ) : (
                      <span className="size-7 shrink-0" aria-hidden />
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </Fragment>
        ))
      )}
    </>
  );
}
