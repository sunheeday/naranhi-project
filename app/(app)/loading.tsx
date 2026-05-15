export default function HomeLoading() {
  return (
    <main className="flex flex-col min-h-screen pb-20">
      <header className="sticky top-0 bg-surface border-b border-border px-6 py-4 flex items-center justify-between z-10">
        <div className="flex flex-col gap-1.5">
          <div className="h-5 w-16 bg-border rounded animate-pulse" />
          <div className="h-4 w-32 bg-border rounded animate-pulse" />
        </div>
        <div className="w-6 h-6 bg-border rounded animate-pulse" />
      </header>

      <section className="px-6 pt-6">
        <div className="h-4 w-20 bg-border rounded animate-pulse mb-4" />
        <ul className="flex flex-col gap-4">
          {[0, 1, 2].map(i => (
            <li key={i} className="bg-surface rounded-card shadow-card p-4">
              <div className="h-5 w-20 bg-border rounded-pill animate-pulse mb-3" />
              <div className="h-5 w-3/4 bg-border rounded animate-pulse mb-2" />
              <div className="h-3 w-16 bg-border rounded animate-pulse" />
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}
