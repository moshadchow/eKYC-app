import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Search } from 'lucide-react'
import { auditAPI } from '@/api/services'
import { Card, Spinner, StatusBadge, EmptyState, AuditTrailModal } from '@/components/ui'

export default function AuditPage() {
  const [page, setPage] = useState(1)
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [selectedEntity, setSelectedEntity] = useState<{type: string; id: string} | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['audit-logs', entityType, action, page],
    queryFn: () => auditAPI.listLogs({ entity_type: entityType || undefined, action: action || undefined, page }).then(r => r.data),
    refetchInterval: 60_000,
  })

  const logs = data?.data ?? []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Activity className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">Audit Trail</h1>
          <p className="text-sm text-surface-500 mt-0.5">Immutable log of all system events</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select className="input w-44" value={entityType} onChange={e => { setEntityType(e.target.value); setPage(1) }}>
          <option value="">All entities</option>
          <option value="kyc_applications">KYC Applications</option>
          <option value="biometric_verifications">Biometric</option>
          <option value="accounts">Accounts</option>
          <option value="sessions">Sessions</option>
          <option value="risk_scores">Risk Scores</option>
          <option value="edd_requests">EDD Requests</option>
        </select>
        <select className="input w-44" value={action} onChange={e => { setAction(e.target.value); setPage(1) }}>
          <option value="">All actions</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="login">Login</option>
          <option value="logout">Logout</option>
          <option value="biometric_success">Biometric Success</option>
          <option value="biometric_failure">Biometric Failure</option>
          <option value="screening_run">Screening Run</option>
          <option value="risk_scored">Risk Scored</option>
          <option value="approval_decision">Decision</option>
          <option value="account_activated">Activated</option>
        </select>
      </div>

      <Card padding={false}>
        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : logs.length === 0 ? (
          <EmptyState icon={<Activity className="h-12 w-12" />} title="No audit logs" description="Events will appear here once actions are performed" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-100 bg-surface-50">
                  {['Time', 'Actor', 'Action', 'Entity', 'Entity ID', 'IP'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-surface-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map((l: any) => (
                  <tr key={l.id} className="border-b border-surface-50 hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-3 text-xs text-surface-500 whitespace-nowrap">
                      {new Date(l.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3">
                      <div className="font-mono text-xs">{l.actor_id?.slice(-8) ?? 'system'}</div>
                      <div className="text-xs text-surface-400">{l.actor_type}</div>
                    </td>
                    <td className="px-5 py-3"><StatusBadge status={l.action} /></td>
                    <td className="px-5 py-3 text-xs text-surface-600">{l.entity_type?.replace(/_/g, ' ')}</td>
                    <td className="px-5 py-3 font-mono text-xs text-brand-600 cursor-pointer hover:underline"
                        onClick={() => setSelectedEntity({ type: l.entity_type, id: l.entity_id })}>
                        {l.entity_id?.slice(-8) ?? '—'}
                      </td>
                    <td className="px-5 py-3 text-xs text-surface-400">{l.ip_address ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > (data.page_size ?? 50) && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-surface-100">
            <span className="text-xs text-surface-500">Showing {logs.length} of {data.total}</span>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
              <button className="btn-secondary btn-sm" onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </Card>

      {/* Entity Drill-down Modal */}
      {selectedEntity && (
        <AuditTrailModal
          entityType={selectedEntity.type}
          entityId={selectedEntity.id}
          open={!!selectedEntity}
          onClose={() => setSelectedEntity(null)}
        />
      )}
    </div>
  )
}
