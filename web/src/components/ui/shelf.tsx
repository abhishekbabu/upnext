import { Link } from "react-router-dom";
import { Poster } from "@/components/ui/poster";

export const SHELF_GRID = "grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-5 gap-y-7";

export function Shelf({ children }: { children: React.ReactNode }) {
  return <ul className={SHELF_GRID}>{children}</ul>;
}

export function ShelfCard({
  titleId,
  name,
  posterPath,
  children,
}: {
  titleId: number;
  name: string;
  posterPath: string | null;
  children?: React.ReactNode;
}) {
  return (
    <li>
      <Link
        to={`/titles/${titleId}`}
        className="group block rounded-md focus-visible:outline-offset-4"
      >
        <Poster name={name} path={posterPath} className="transition-opacity group-hover:opacity-85" />
        <p className="mt-2.5 truncate text-[13.5px] font-medium leading-snug" title={name}>
          {name}
        </p>
        {children}
      </Link>
    </li>
  );
}
