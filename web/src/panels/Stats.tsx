import { PageHeader } from "@/components/ui/page-header";
import { Failed, Loading } from "@/components/ui/state";
import { STATUSES, STATUS_LABELS, type Status } from "@/lib/api";
import { hours, shortDate } from "@/lib/format";
import { useStats } from "@/lib/queries";

/** The library in figures. */
export function Stats() {
  const { data, isPending, error } = useStats();

  if (error) return <Failed error={error} />;
  if (isPending) return <Loading />;

  const runtime = hours(data.known_minutes);

  return (
    <>
      <PageHeader title="Stats" detail="What the library adds up to." />

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="Watches" value={data.watches.toLocaleString()} />
        <Figure label="Episodes" value={data.episodes_watched.toLocaleString()} />
        <Figure label="Titles" value={data.titles_watched.toLocaleString()} />
        {/* Labelled "at least" because only enriched episodes carry a runtime,
            so this is a floor rather than a total — see `Library.stats`. */}
        <Figure label="At least" value={runtime || "—"} />
      </dl>

      {data.first_watch && (
        <p className="mt-5 font-mono text-[11.5px] text-muted-foreground">
          {shortDate(data.first_watch)} — {shortDate(data.last_watch)}
        </p>
      )}

      <h2 className="mb-3 mt-10 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        By status
      </h2>
      <dl className="grid max-w-md gap-px overflow-hidden rounded-md border border-border bg-border">
        {STATUSES.filter((status) => data.by_status[status]).map((status) => (
          <div key={status} className="flex items-baseline justify-between bg-card px-3.5 py-2.5">
            <dt className="text-[13.5px]">{STATUS_LABELS[status as Status]}</dt>
            <dd className="font-mono text-[13px]">{data.by_status[status]}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card px-3.5 py-3">
      <dt className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 font-display text-xl font-semibold tracking-tight">{value}</dd>
    </div>
  );
}
