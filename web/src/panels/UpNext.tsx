import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/page-header";
import { Poster } from "@/components/ui/poster";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { episodeCode, shortDate } from "@/lib/format";
import { useConfig, useUpNext } from "@/lib/queries";

/**
 * The shelf this app exists for: the next unwatched episode of everything in
 * progress, most recently watched first.
 *
 * "Next" is decided by the server — the lowest-numbered unwatched episode,
 * which is the only definition that survives someone skipping around. Nothing
 * here re-derives it.
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
    </>
  );
}
