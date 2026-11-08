import { useMemo } from "react";
import { ListControls } from "@/components/ui/list-controls";
import { PageHeader } from "@/components/ui/page-header";
import { Shelf, ShelfCard } from "@/components/ui/shelf";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { WatchButton } from "@/components/ui/watch-button";
import type { UpNextItem } from "@/lib/api";
import { episodeCode, shortDate } from "@/lib/format";
import { byName, descending, narrow, useListParams, type SortOption } from "@/lib/list";
import { useUpNext } from "@/lib/queries";

/**
 * The shelf this app exists for: the next unwatched episode of everything in
 * progress, most recently watched first.
 *
 * "Next" is decided by the server — the lowest-numbered unwatched episode,
 * which is the only definition that survives someone skipping around. Nothing
 * here re-derives it.
 *
 * The backlog, where the timeline is the schedule: what to put on now, rather
 * than what has just come out or is coming. Separate questions, separate
 * queries, neither folded into the other.
 */
const SORTS: readonly SortOption<UpNextItem>[] = [
  { value: "recent", label: "Recently watched", compare: null },
  { value: "name", label: "Name", compare: byName },
  // Air dates are YYYY-MM-DD, so they order as text.
  { value: "newest", label: "Newest episode", compare: descending((item) => item.air_date) },
];

export function UpNext() {
  const { data, isPending, error } = useUpNext();
  const { search, sort, set } = useListParams(SORTS);
  const shown = useMemo(() => narrow(data ?? [], search, sort), [data, search, sort]);

  return (
    <>
      <PageHeader title="Up next" detail="The next episode of everything you have started." />
      <ListControls
        search={search}
        onSearch={(value) => set("q", value)}
        sorts={SORTS}
        sort={sort}
        onSort={(value) => set("sort", value === SORTS[0]!.value ? null : value)}
      />
      {error ? (
        <Failed error={error} />
      ) : isPending ? (
        <Loading shape="shelf" />
      ) : data.length === 0 ? (
        <Empty
          title="Nothing in progress"
          detail="Shows you are part-way through appear here. Import a library and enrich it, then start watching."
        />
      ) : shown.length === 0 ? (
        <Empty
          title={`Nothing matching “${search}”`}
          detail="Try a shorter fragment — the filter matches anywhere in the name."
        />
      ) : (
        <Shelf>
          {shown.map((item) => (
            <ShelfCard key={item.episode_id} titleId={item.title_id} name={item.name} posterPath={item.poster_path}>
              <div className="mt-0.5 flex items-center justify-between gap-2">
                <p className="font-mono text-[11px] text-muted-foreground">
                  {episodeCode(item.season_number, item.episode_number)}
                </p>
                <WatchButton episodeId={item.episode_id} season={item.season_number} episode={item.episode_number} />
              </div>
              {item.episode_name && (
                <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{item.episode_name}</p>
              )}
              {item.last_watched_at && (
                <p className="mt-1 font-mono text-[10.5px] text-muted-foreground/80">
                  last watched {shortDate(item.last_watched_at)}
                </p>
              )}
            </ShelfCard>
          ))}
        </Shelf>
      )}
    </>
  );
}
