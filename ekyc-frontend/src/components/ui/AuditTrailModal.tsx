import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, X } from 'lucide-react'
import { auditAPI } from '@/api/services'
import { Spinner, EmptyState } from './index'

interface AuditTrailModalProps {
  entityType: string
  entityId: string
  open: boolean
  onClose: () => void
}

interface AuditEvent {
  id: string
  actor_id: string | null
  actor_type: string | null
  action: string
  old_value: string | null
  new_value: string | null
  ip_address: string | null
  created_at: string
}

function formatJson(value: string | null): string {
  if (!value) return '-'
  try {
    const parsed = JSON.parse(value)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return value
  }
}

export function AuditTrailModal({ entityType, entityId, open, onClose }: AuditTrailModalProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['audit-trail', entityType, entityId],
    queryFn: () => auditAPI.entityTrail(entityType, entityId).then(r => r.data.data ?? []),
    enabled: open,
  })

  if (!open) return null

  const events = (data as AuditEvent[]) ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-modal w-full max-w-2xl max-h-[80vh] flex flex-col animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-brand-600" />
            <div>
              <h2 className="font-semibold text-surface-900">Audit Trail</h2>
              <p className="text-xs text-surface-500">
                {entityType.replace(/_/g, ' ')} — <span className="font-mono">{entityId.slice(0, 8)}...</span>
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-surface-400 hover:text-surface-600 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Spinner size="lg" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-danger">
              Failed to load audit trail
            </div>
          ) : events.length === 0 ? (
            <EmptyState
              icon={<Activity className="h-10 w-10" />}
              title="No events found"
              description="This entity has no audit events"
            />
          ) : (
            <div className="space-y-4">
              {events.map((event) => (
                <div key={event.id} className="border border-surface-200 rounded-lg p-4 bg-surface-50">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-surface-600 uppercase">
                        {event.action.replace(/_/g, ' ')}
                      </span>
                      {event.actor_type && (
                        <span className="text-xs text-surface-400">
                          by {event.actor_type}:{event.actor_id?.slice(-8) ?? 'system'}
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-surface-400">
                      {new Date(event.created_at).toLocaleString()}
                    </span>
                  </div>
                  {(event.old_value || event.new_value) && (
                    <div className="mt-2 text-xs font-mono bg-white rounded p-2 border border-surface-200">
                      {event.old_value && (
                        <div className="mb-1">
                          <span className="text-surface-500">Before: </span>
                          <span className="text-surface-700">{formatJson(event.old_value)}</span>
                        </div>
                      )}
                      {event.new_value && (
                        <div>
                          <span className="text-surface-500">After: </span>
                          <span className="text-brand-600">{formatJson(event.new_value)}</span>
                        </div>
                      )}
                    </div>
                  )}
                  {event.ip_address && (
                    <div className="mt-2 text-xs text-surface-400">IP: {event.ip_address}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-surface-100 bg-surface-50 rounded-b-2xl flex justify-end">
          <button onClick={onClose} className="btn-secondary btn-sm">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}