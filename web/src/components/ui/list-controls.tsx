import { Select } from "@/components/ui/select";
import type { SortOption } from "@/lib/list";
import { cn } from "@/lib/utils";

/**
 * Search and sort for a shelf, with room on the left for the page's own
 * filters (the Library's status tabs). Controlled: `useListParams` owns the
 * state, in the address.
 */
export function ListControls<T>({
  search,
  onSearch,
  sorts,
  sort,
  onSort,
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  sorts: readonly SortOption<T>[];
  sort: SortOption<T>;
  onSort: (value: string) => void;
  children?: React.ReactNode;
}) {
  const field = "rounded-md border border-border bg-card px-2.5 py-1.5 text-[13px]";
  return (
    <div className="mb-6 flex flex-wrap items-center gap-2">
      {children}
      <div className="ml-auto flex items-center gap-2">
        <Select aria-label="Sort" value={sort.value} onChange={(event) => onSort(event.target.value)} className={field}>
          {sorts.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <input
          type="search"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Filter by name"
          aria-label="Filter by name"
          className={cn(field, "w-52 placeholder:text-muted-foreground")}
        />
      </div>
    </div>
  );
}
