export default function DraftingLoading() {
  return (
    <div className="flex flex-col h-full overflow-hidden animate-pulse">
      {/* Tab bar skeleton */}
      <div className="h-10 bg-slate-100 border-b border-slate-200 shrink-0" />

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar skeleton */}
        <div className="w-56 shrink-0 border-r border-slate-200 p-3 space-y-2">
          <div className="h-16 bg-slate-100 rounded-lg" />
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-8 bg-slate-100 rounded-lg" />
          ))}
        </div>

        {/* Main area skeleton */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Intelligence panel */}
          <div className="h-24 border-b border-slate-200 bg-slate-50 m-3 rounded-lg" />

          <div className="flex flex-1 overflow-hidden gap-3 p-3">
            {/* Chat skeleton */}
            <div className="flex-1 space-y-3">
              <div className="h-6 bg-slate-100 rounded w-1/4" />
              <div className="h-20 bg-slate-100 rounded-xl" />
              <div className="h-14 bg-slate-100 rounded-xl w-3/4" />
            </div>
            {/* Studio skeleton */}
            <div className="w-[480px] space-y-2">
              <div className="h-8 bg-slate-100 rounded" />
              <div className="h-full bg-slate-100 rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
