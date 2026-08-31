import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { StatusBadge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Poster } from "@/components/ui/poster";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Empty, Failed, Loading } from "@/components/ui/state";
import { STATUSES, STATUS_LABELS, type Status } from "@/lib/api";
import { progress } from "@/lib/format";
import { useConfig, useTitles } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Everything, filterable by status and searchable by name. */
export function Library() {
  const [params, setParams] = useSearchParams();
  const status = asStatus(params.get("status"));
  const [search, setSearch] = useState("");

  const config = useConfig();
  const { data, isPending, error } = useTitles(status);

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return data ?? [];
    return (data ?? []).filter((title) => title.name.toLowerCase().includes(needle));
  }, [data, search]);

  return (
    <>
      <PageHeader title="Library" detail="Everything upnext knows you have watched, or mean to." />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <FilterTab active={!status} onClick={() => setStatus(setParams, null)}>
          All
        </FilterTab>
        {STATUSES.map((value) => (
          <FilterTab key={value} active={status === value} onClick={() => setStatus(setParams, value)}>
            {STATUS_LABELS[value]}
          </FilterTab>
        ))}
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Filter by name"
          aria-label="Filter by name"
          className={cn(
            "ml-auto w-52 rounded-md border border-border bg-card px-2.5 py-1.5",
            "text-[13px] placeholder:text-muted-foreground",
          )}
        />
      </div>

      {error ? (
        <Failed error={error} />
      ) : isPending || config.isPending ? (
        <Loading shape="shelf" />
      ) : shown.length === 0 ? (
        <Empty
          title={search ? `Nothing matching “${search}”` : "Nothing here yet"}
          detail={
            search
              ? "Try a shorter fragment — the filter matches anywhere in the name."
              : "Run `just import <export-dir>` to build a library, then `just enrich` to give it artwork."
          }
        />
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-5 gap-y-7">
          {shown.map((title) => {
            const share = progress(title);
            return (
              <li key={title.id}>
                <Link
                  to={`/titles/${title.id}`}
                  className="group block rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                >
                  <Poster
                    name={title.name}
                    path={title.poster_path}
                    base={config.data?.image_base ?? ""}
                    className="transition-opacity group-hover:opacity-85"
                  />
                  <p className="mt-2.5 truncate text-[13.5px] font-medium leading-snug" title={title.name}>
                    {title.name}
                  </p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <StatusBadge status={title.status} />
                    {title.year && <span className="font-mono text-[10.5px] text-muted-foreground">{title.year}</span>}
                  </div>
                  {share !== null && (
                    <>
                      <ProgressBar value={share} className="mt-2" />
                      <p className="mt-1 font-mono text-[10.5px] text-muted-foreground">
                        {title.episodes_watched} / {title.total_episodes}
                      </p>
                    </>
                  )}
                  {/* No bar without a catalog count — see `progress`. The count
                      alone is still worth showing, because it is real. */}
                  {share === null && title.episodes_watched > 0 && (
                    <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">
                      {title.episodes_watched} watched
                    </p>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
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

function setStatus(setParams: ReturnType<typeof useSearchParams>[1], status: Status | null) {
  setParams(status ? { status } : {}, { replace: true });
}
