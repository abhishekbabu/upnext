export function PageHeader({ title, detail }: { title: string; detail?: string }) {
  return (
    <header className="mb-6">
      <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
      {detail && <p className="mt-1 text-[13.5px] text-muted-foreground">{detail}</p>}
    </header>
  );
}
