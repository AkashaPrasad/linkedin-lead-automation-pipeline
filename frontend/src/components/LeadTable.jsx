const CATEGORY_COLORS = {
  'FMCG': 'bg-green-accent/10 text-green-accent border-green-accent/20',
  'Real Estate': 'bg-purple-primary/10 text-purple-light border-purple-primary/20',
  'Apparel': 'bg-amber-accent/10 text-amber-accent border-amber-accent/20',
  'Kids': 'bg-blue-400/10 text-blue-400 border-blue-400/20',
  'Beauty': 'bg-orange-400/10 text-orange-400 border-orange-400/20',
  'Generic': 'bg-text-muted/10 text-text-secondary border-text-muted/20',
}

const STATUS_COLORS = {
  'SENT': 'text-green-accent',
  'PENDING': 'text-amber-accent',
  'FAILED': 'text-red-accent',
  'NO_EMAIL': 'text-text-muted',
  'CAPPED': 'text-amber-accent',
}

export default function LeadTable({ leads }) {
  return (
    <div className="bg-bg-secondary rounded-xl border border-border-color flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border-color flex items-center justify-between flex-shrink-0">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">Live Leads</h3>
        <span className="text-xs text-text-muted">{leads.length} found</span>
      </div>

      <div className="overflow-auto flex-1">
        {leads.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-text-muted text-sm">
            Leads will appear here as the pipeline runs
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-bg-secondary">
              <tr className="border-b border-border-color">
                <th className="text-left px-4 py-2 text-text-muted font-medium">Name</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium hidden lg:table-cell">Headline</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium">Category</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium hidden md:table-cell">Email</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead, i) => (
                <tr
                  key={i}
                  className="border-b border-border-color/50 hover:bg-bg-tertiary/30 animate-slide-in"
                >
                  <td className="px-4 py-2.5 font-medium text-text-primary max-w-[120px] truncate">
                    {lead.name || '—'}
                  </td>
                  <td className="px-4 py-2.5 text-text-secondary hidden lg:table-cell max-w-[200px] truncate">
                    {lead.headline || '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`px-2 py-0.5 rounded-full border text-xs font-medium ${CATEGORY_COLORS[lead.category] || CATEGORY_COLORS['Generic']}`}>
                      {lead.category || 'Generic'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-text-secondary hidden md:table-cell max-w-[160px] truncate">
                    {lead.email || '—'}
                  </td>
                  <td className={`px-4 py-2.5 font-medium ${STATUS_COLORS[lead.status] || 'text-text-muted'}`}>
                    {lead.status || 'PENDING'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
