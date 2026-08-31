import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import { Library } from "@/panels/Library";
import { Stats } from "@/panels/Stats";
import { Title } from "@/panels/Title";
import { UpNext } from "@/panels/UpNext";
import { useTheme } from "@/lib/useTheme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Up next" },
  { to: "/library", label: "Library" },
  { to: "/stats", label: "Stats" },
];

/**
 * One layout for every page. The rail and the panel read the same address, so
 * routing swaps the panel rather than re-rendering the shell around it.
 */
export default function App() {
  const { mode, setMode } = useTheme();

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-(--container-page) items-center gap-6 px-5 py-3">
          <span className="font-display text-[15px] font-semibold tracking-tight">upnext</span>
          <nav className="flex items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                    isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => setMode(mode === "dark" ? "light" : "dark")}
            className="ml-auto rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {mode === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-(--container-page) px-5 py-8">
        <Routes>
          <Route path="/" element={<UpNext />} />
          <Route path="/library" element={<Library />} />
          <Route path="/titles/:id" element={<Title />} />
          <Route path="/stats" element={<Stats />} />
          {/* An address nobody wrote a route for is a mistyped link, not a
              blank page. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
