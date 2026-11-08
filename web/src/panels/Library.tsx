import { useMemo } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { ListControls } from "@/components/ui/list-controls";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Shelf, ShelfCard } from "@/components/ui/shelf";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { STATUSES, STATUS_LABELS, type Status, type TitleSummary } from "@/lib/api";
import { progressOf } from "@/lib/format";
import { byName, descending, narrow, useListParams, type SortOption } from "@/lib/list";
import { useTitles } from "@/lib/queries";
import { cn } from "@/lib/utils";

const SORTS: readonly SortOption<TitleSummary>[] = [
  { value: "recent", label: "Recently watched", compare: null },
  { value: "name", label: "Name", compare: byName },
  { value: "year", label: "Newest", compare: descending((title) => title.year) },
  {
    value: "progress",
    label: "Progress",
    // Only a measured share is progress; a bare count has nothing to divide by.
    compare: descending((title) => {
      const progress = progressOf(title);
      return progress.kind === "measured" ? progress.share : null;
    }),
  },
];

/** Everything, filterable by status, searchable by name, and sortable. */
export function Library() {
  const { params, search, sort, set } = useListParams(SORTS);
  const status = asStatus(params.get("status"));

  const { data, isPending, error } = useTitles(status);
  const shown = useMemo(() => narrow(data ?? [], search, sort), [data, search, sort]);

  return (
    <>
      <PageHeader title="Library" detail="Everything upnext knows you have watched, or mean to." />

      <ListControls
        search={search}
        onSearch={(value) => set("q", value)}
        sorts={SORTS}
        sort={sort}
        onSort={(value) => set("sort", value === SORTS[0]!.value ? null : value)}
      >
        <FilterTab active={!status} onClick={() => set("status", null)}>
          All
        </FilterTab>
        {STATUSES.map((value) => (
          <FilterTab key={value} active={status === value} onClick={() => set("status", value)}>
            {STATUS_LABELS[value]}
          </FilterTab>
        ))}
      </ListControls>

      {error ? (
        <Failed error={error} />
      ) : isPending ? (
        <Loading shape="shelf" />
      ) : shown.length === 0 ? (
        <Empty
          title={
            search
              ? `Nothing matching “${search}”`
              : status
                ? `Nothing marked ${STATUS_LABELS[status].toLowerCase()}`
                : "Nothing here yet"
          }
          detail={
            search
              ? "Try a shorter fragment — the filter matches anywhere in the name."
              : status
                ? undefined
                : "Run `just import <export-dir>` to build a library, then `just enrich` to give it artwork."
          }
        />
      ) : (
        <Shelf>
          {shown.map((title) => {
            const progress = progressOf(title);
            return (
              <ShelfCard key={title.id} titleId={title.id} name={title.name} posterPath={title.poster_path}>
                <div className="mt-1 flex items-center gap-1.5">
                  <StatusBadge status={title.status} />
                  {title.year && <span className="font-mono text-[10.5px] text-muted-foreground">{title.year}</span>}
                </div>
                {progress.kind === "measured" && (
                  <>
                    <ProgressBar value={progress.share} label={title.name} className="mt-2" />
                    <p className="mt-1 font-mono text-[10.5px] text-muted-foreground">
                      {progress.watched} / {progress.total}
                    </p>
                  </>
                )}
                {progress.kind === "counted" && (
                  <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">{progress.watched} watched</p>
                )}
                {progress.kind === "unenriched" && (
                  <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">
                    {progress.watched} watched · not enriched
                  </p>
                )}
                {progress.kind === "unmatched" && (
                  <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">
                    {progress.unmatched} watched · none on TMDB&rsquo;s list
                  </p>
                )}
              </ShelfCard>
            );
          })}
        </Shelf>
      )}
    </>
  );
}

function FilterTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
        active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary",
      )}
    >
      {children}
    </button>
  );
}

/**
 * The filter lives in the URL so a filtered shelf can be linked and survives a
 * reload. An unknown value falls back to "all" rather than showing nothing.
 */
function asStatus(value: string | null): Status | undefined {
  return STATUSES.includes(value as Status) ? (value as Status) : undefined;
}
