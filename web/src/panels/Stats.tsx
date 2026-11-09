import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/ui/page-header";
import { Failed, Loading } from "@/components/ui/state";
import { STATUSES, STATUS_LABELS, type Activity, type Period, type TitleTotal } from "@/lib/api";
import { count, counted, hourName, hours, monthName, shortDate, weekdays } from "@/lib/format";
import { useActivity, useStats } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** The library in figures: what it adds up to, then when and what was watched. */
export function Stats() {
  const { data, isPending, error } = useStats();
  const activity = useActivity();

  if (error) return <Failed error={error} />;
  if (isPending) return <Loading />;

  const runtime = hours(data.known_minutes);
  const statuses = STATUSES.filter((status) => data.by_status[status]);

  return (
    <>
      <PageHeader title="Stats" detail="What the library adds up to." />

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure label="Watches" value={count(data.watches)} />
        <Figure label="Episodes" value={count(data.distinct_episodes)} />
        <Figure label="Titles" value={count(data.titles_watched)} />
        {/* A floor, not a total: only enriched episodes carry a runtime. */}
        <Figure label="At least" value={runtime || "—"} />
      </dl>

      {data.first_watch && (
        <p className="mt-5 font-mono text-[11.5px] text-muted-foreground">
          {shortDate(data.first_watch)} — {shortDate(data.last_watch)}
        </p>
      )}

      {activity.error ? (
        <div className="mt-10">
          <Failed error={activity.error} />
        </div>
      ) : activity.isPending ? (
        <div className="mt-10">
          <Loading />
        </div>
      ) : (
        <ActivitySections activity={activity.data} />
      )}

      {statuses.length > 0 && (
        <>
          <h2 className="eyebrow mb-3 mt-10">By status</h2>
          <dl className="grid max-w-md gap-px overflow-hidden rounded-md border border-border bg-border">
            {statuses.map((status) => (
              <div key={status} className="flex items-baseline justify-between bg-card px-3.5 py-2.5">
                <dt className="text-[13.5px]">{STATUS_LABELS[status]}</dt>
                <dd className="font-mono text-[13px]">{data.by_status[status]}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </>
  );
}

function ActivitySections({ activity }: { activity: Activity }) {
  const { longest_streak: longest, busiest_day: busiest, biggest_binge: binge } = activity;

  return (
    <>
      <h2 className="eyebrow mb-3 mt-10">Records</h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Figure
          label="Longest streak"
          value={longest ? counted(longest.days, "day") : "—"}
          detail={longest && `${shortDate(longest.start)} — ${shortDate(longest.end)}`}
        />
        <Figure
          label="Current streak"
          value={activity.current_streak ? counted(activity.current_streak, "day") : "—"}
          detail={activity.current_streak ? "and counting" : "nothing watched yesterday or today"}
        />
        <Figure
          label="Busiest day"
          value={busiest ? counted(busiest.viewings, "episode") : "—"}
          detail={busiest && shortDate(busiest.date)}
        />
        <Figure
          label="Biggest binge"
          value={binge ? counted(binge.viewings, "episode") : "—"}
          detail={
            binge && (
              <>
                <Link to={`/titles/${binge.title_id}`} className="hover:text-foreground hover:underline">
                  {binge.name}
                </Link>{" "}
                · {shortDate(binge.date)}
              </>
            )
          }
        />
      </dl>

      {activity.bulk > 0 && (
        <p className="mt-4 max-w-[70ch] text-[12.5px] leading-relaxed text-muted-foreground">
          {counted(activity.bulk, "viewing")} were logged in bulk (a season ticked off at once), so their timestamps
          say when they were logged, not watched. They count toward Most watched, and are left out of the records and
          charts here.
        </p>
      )}

      {activity.months.length > 0 && (
        <>
          <h2 className="eyebrow mb-3 mt-10">Episodes by month</h2>
          <Months months={activity.months} />
        </>
      )}

      {activity.dated > 0 && (
        <>
          <h2 className="eyebrow mb-3 mt-10">When you watch</h2>
          <Rhythm rhythm={activity.rhythm} timezone={activity.timezone} />
        </>
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        {activity.years.length > 0 && (
          <section>
            <h2 className="eyebrow mb-3">By year</h2>
            <Years years={activity.years} />
          </section>
        )}
        {activity.top_titles.length > 0 && (
          <section>
            <h2 className="eyebrow mb-3">Most watched</h2>
            <TopTitles titles={activity.top_titles} />
          </section>
        )}
      </div>
    </>
  );
}

/**
 * One column per month, empty months included, so a gap in the chart is a gap
 * in the watching. Hover (or tap) a month for its figures; the year table below
 * is the same data as text.
 */
function Months({ months }: { months: Period[] }) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...months.map((month) => month.viewings));
  const shown = active === null ? null : months[active];
  const peak = months.reduce((best, month) => (month.viewings > best.viewings ? month : best), months[0]!);

  return (
    <figure className="rounded-md border border-border bg-card p-4">
      <figcaption className="h-5 font-mono text-[11.5px] text-muted-foreground">
        {shown ? (
          <>
            <span className="text-foreground">{monthName(shown.label)}</span> · {counted(shown.viewings, "episode")}
            {hours(shown.minutes) && ` · ${hours(shown.minutes)}`}
          </>
        ) : (
          <>
            Busiest: <span className="text-foreground">{monthName(peak.label)}</span>, {counted(peak.viewings, "episode")}
          </>
        )}
      </figcaption>
      <div
        className="mt-3 flex h-36 items-end gap-[2px] border-b border-border"
        onMouseLeave={() => setActive(null)}
        aria-hidden
      >
        {months.map((month, index) => (
          <div
            key={month.label}
            className="flex h-full min-w-0 flex-1 items-end"
            onMouseEnter={() => setActive(index)}
            onClick={() => setActive(index)}
          >
            <div
              className={cn(
                "w-full rounded-t-[3px] transition-opacity",
                active !== null && active !== index ? "opacity-45" : "opacity-100",
              )}
              style={{
                height: `${(month.viewings / max) * 100}%`,
                backgroundColor: "var(--color-accent-foreground)",
              }}
            />
          </div>
        ))}
      </div>
      {/* A year label under each January, placed by its share of the run. */}
      <div className="relative mt-1.5 h-4 font-mono text-[10.5px] text-muted-foreground" aria-hidden>
        {months.map((month, index) =>
          month.label.endsWith("-01") || index === 0 ? (
            <span key={month.label} className="absolute" style={{ left: `${(index / months.length) * 100}%` }}>
              {month.label.slice(0, 4)}
            </span>
          ) : null,
        )}
      </div>
    </figure>
  );
}

/**
 * Viewings by weekday and hour, in one hue from faint to full. Hover a cell for
 * its count.
 */
function Rhythm({ rhythm, timezone }: { rhythm: number[][]; timezone: string }) {
  const [active, setActive] = useState<[number, number] | null>(null);
  const max = Math.max(1, ...rhythm.flat());
  const days = weekdays();
  const longDays = weekdays(undefined, "long");
  const [peakDay, peakHour] = rhythm.reduce<[number, number]>(
    (best, hours, day) =>
      hours.reduce<[number, number]>((b, n, hour) => (n > rhythm[b[0]]![b[1]]! ? [day, hour] : b), best),
    [0, 0],
  );
  const [day, hour] = active ?? [peakDay, peakHour];

  return (
    <figure className="rounded-md border border-border bg-card p-4">
      <figcaption className="h-5 font-mono text-[11.5px] text-muted-foreground">
        {active ? "" : "Most often: "}
        <span className="text-foreground">
          {longDays[day]}, {hourName(hour)}
        </span>{" "}
        · {counted(rhythm[day]![hour]!, "episode")}
      </figcaption>
      <div className="mt-3 overflow-x-auto">
        <div className="grid min-w-[34rem] grid-cols-[2.5rem_repeat(24,minmax(0,1fr))] gap-[2px]" aria-hidden>
          <span />
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="font-mono text-[10px] text-muted-foreground">
              {h % 6 === 0 ? hourName(h) : ""}
            </span>
          ))}
          {rhythm.map((hours, d) => (
            <Row key={d} label={days[d]!}>
              {hours.map((n, h) => (
                <div
                  key={h}
                  className={cn("h-6 rounded-[2px]", active?.[0] === d && active[1] === h && "ring-1 ring-foreground")}
                  style={{ backgroundColor: shade(n, max) }}
                  onMouseEnter={() => setActive([d, h])}
                  onMouseLeave={() => setActive(null)}
                  onClick={() => setActive([d, h])}
                />
              ))}
            </Row>
          ))}
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-4 font-mono text-[10.5px] text-muted-foreground">
        <span>Times in {timezone.replaceAll("_", " ")}</span>
        <span className="flex items-center gap-1.5" aria-hidden>
          Fewer
          {[0, 0.25, 0.5, 0.75, 1].map((share) => (
            <span key={share} className="size-2.5 rounded-[2px]" style={{ backgroundColor: shade(share, 1) }} />
          ))}
          More
        </span>
      </div>
    </figure>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <span className="self-center font-mono text-[10.5px] text-muted-foreground">{label}</span>
      {children}
    </>
  );
}

/** One hue, faint to full: nothing is the bare track, anything at all is visible. */
function shade(n: number, max: number): string {
  if (n <= 0) return "var(--color-secondary)";
  const share = 18 + Math.round((n / max) * 82);
  return `color-mix(in oklab, var(--color-accent-foreground) ${share}%, var(--color-secondary))`;
}

function Years({ years }: { years: Period[] }) {
  return (
    <table className="w-full overflow-hidden rounded-md border border-border text-[13px]">
      <thead className="bg-card text-left">
        <tr className="eyebrow text-[10.5px]">
          <th className="px-3.5 py-2 font-medium">Year</th>
          <th className="px-3.5 py-2 text-right font-medium">Episodes</th>
          <th className="px-3.5 py-2 text-right font-medium">Hours</th>
          <th className="px-3.5 py-2 text-right font-medium">Titles</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border border-t border-border font-mono">
        {[...years].reverse().map((year) => (
          <tr key={year.label}>
            <td className="px-3.5 py-2">{year.label}</td>
            <td className="px-3.5 py-2 text-right">{count(year.viewings)}</td>
            <td className="px-3.5 py-2 text-right">{year.minutes >= 60 ? count(Math.floor(year.minutes / 60)) : "—"}</td>
            <td className="px-3.5 py-2 text-right">{count(year.titles)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TopTitles({ titles }: { titles: TitleTotal[] }) {
  const max = Math.max(1, ...titles.map((title) => title.viewings));

  return (
    <ol className="space-y-2.5">
      {titles.map((title, index) => (
        <li key={title.title_id} className="grid grid-cols-[1.25rem_minmax(0,1fr)_6.5rem] items-center gap-x-3">
          <span className="font-mono text-[11px] text-muted-foreground">{index + 1}</span>
          <div className="min-w-0">
            <Link to={`/titles/${title.title_id}`} className="block truncate text-[13.5px] hover:underline">
              {title.name}
            </Link>
            <div className="mt-1 h-1.5 rounded-full bg-secondary">
              <div
                className="h-full rounded-full"
                style={{ width: `${(title.viewings / max) * 100}%`, backgroundColor: "var(--color-accent-foreground)" }}
              />
            </div>
          </div>
          <span className="text-right font-mono text-[11.5px] text-muted-foreground">
            {count(title.viewings)}
            {title.minutes >= 60 && ` · ${count(Math.floor(title.minutes / 60))} h`}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Figure({ label, value, detail }: { label: string; value: string; detail?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-card px-3.5 py-3">
      <dt className="eyebrow text-[10.5px]">{label}</dt>
      <dd className="mt-1 font-display text-xl font-semibold tracking-tight">{value}</dd>
      {detail && <dd className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{detail}</dd>}
    </div>
  );
}
