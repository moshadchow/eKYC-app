import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Eye, UserCheck, AlertTriangle, Clock, CheckCircle2, XCircle, Filter, RefreshCw } from 'lucide-react'
import { adminAPI, complianceAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, StatusBadge, Alert, Spinner, Modal, Select, EmptyState, SkeletonCard } from '@/components/ui'
import type { QueueEntry, ReviewSummary, DecisionRequest } from '@/types/api'

export default function AgentQueuePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [queueTypeFilter, setQueueTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [selectedApp, setSelectedApp] = useState<string | null>(null)
  const [decisionModal, setDecisionModal] = useState(false)
  const [action, setAction] = useState<string>('approve')
  const [notes, setNotes] = useState('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [error, setError] = useState('')

  const { data: queue, isLoading, refetch } = useQuery({
    queryKey: ['queue', queueTypeFilter, statusFilter, page],
    queryFn: () => adminAPI.listQueue({ queue_type: queueTypeFilter || undefined, status: statusFilter || undefined, page }).then(r => r.data),
    refetchInterval: 30_000,
  })

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['review-summary', selectedApp],
    queryFn: () => selectedApp ? adminAPI.reviewSummary(selectedApp).then(r => r.data.data) : null,
    enabled: !!selectedApp,
  })

  const decideMutation = useMutation({
    mutationFn: ({ appId, body }: { appId: string; body: DecisionRequest }) => adminAPI.decide(appId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queue'] })
      setDecisionModal(false)
      setSelectedApp(null)
      setNotes('')
      setRejectionReason('')
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const activateMutation = useMutation({
    mutationFn: (appId: string) => adminAPI.activate(appId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['queue'] }); setSelectedApp(null) },
    onError: (err) => setError(getErrorMessage(err)),
  })

  function handleDecide() {
    if (!selectedApp) return
    decideMutation.mutate({
      appId: selectedApp,
      body: { action: action as any, notes: notes || undefined, rejection_reason: action === 'reject' ? rejectionReason : undefined },
    })
  }

  const queueItems = queue?.data ?? []

  const stats = {
    total: queue?.total ?? 0,
    unassigned: queueItems.filter(e => e.status === 'unassigned').length,
    in_review: queueItems.filter(e => e.status === 'in_review').length,
    high_risk: queueItems.filter(e => e.queue_type === 'high_risk').length,
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="text-sm text-surface-500 mt-0.5">Maker-checker approval workflow</p>
        </div>
        <button onClick={() => refetch()} className="btn-secondary btn-sm"><RefreshCw className="h-4 w-4" /> Refresh</button>
      </div>

      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total', value: stats.total, icon: <Clock className="h-5 w-5 text-brand-600" />, color: 'bg-brand-50' },
          { label: 'Unassigned', value: stats.unassigned, icon: <AlertTriangle className="h-5 w-5 text-warning" />, color: 'bg-warning-light' },
          { label: 'In Review', value: stats.in_review, icon: <UserCheck className="h-5 w-5 text-info" />, color: 'bg-info-light' },
          { label: 'High Risk', value: stats.high_risk, icon: <XCircle className="h-5 w-5 text-danger" />, color: 'bg-danger-light' },
        ].map(s => (
          <Card key={s.label} className="p-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${s.color}`}>{s.icon}</div>
              <div>
                <div className="text-2xl font-semibold text-surface-900">{s.value}</div>
                <div className="text-xs text-surface-500">{s.label}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <Filter className="h-4 w-4 text-surface-400" />
        <Select value={queueTypeFilter} onChange={e => setQueueTypeFilter(e.target.value)} className="w-44">
          <option value="">All queue types</option>
          <option value="standard">Standard</option>
          <option value="high_risk">High Risk</option>
          <option value="failed_verification">Failed Verification</option>
          <option value="edd_pending">EDD Pending</option>
        </Select>
        <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="w-40">
          <option value="">All statuses</option>
          <option value="unassigned">Unassigned</option>
          <option value="in_review">In Review</option>
          <option value="completed">Completed</option>
        </Select>
      </div>

      {/* Queue table */}
      <Card padding={false}>
        {isLoading ? (
          <div className="p-6 space-y-3">{Array(4).fill(0).map((_, i) => <SkeletonCard key={i} />)}</div>
        ) : queueItems.length === 0 ? (
          <EmptyState icon={<CheckCircle2 className="h-12 w-12" />} title="Queue is empty" description="No applications pending review" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-100">
                  {['Application Ref', 'Queue Type', 'Priority', 'Status', 'Submitted', 'Actions'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-surface-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queueItems.map((entry) => (
                  <tr key={entry.id} className="border-b border-surface-50 hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-xs bg-surface-100 px-2 py-0.5 rounded">{entry.app_id.slice(-8)}</span>
                    </td>
                    <td className="px-5 py-3.5"><StatusBadge status={entry.queue_type} /></td>
                    <td className="px-5 py-3.5"><StatusBadge status={entry.priority} /></td>
                    <td className="px-5 py-3.5"><StatusBadge status={entry.status} /></td>
                    <td className="px-5 py-3.5 text-surface-500 text-xs">{new Date(entry.created_at).toLocaleDateString()}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex gap-2">
                        <button
                          className="btn-secondary btn-sm"
                          onClick={() => setSelectedApp(entry.app_id)}
                        >
                          <Eye className="h-3.5 w-3.5" /> Review
                        </button>
                        {entry.status !== 'completed' && (
                          <button
                            className="btn-primary btn-sm"
                            onClick={() => { setSelectedApp(entry.app_id); setDecisionModal(true) }}
                          >
                            <UserCheck className="h-3.5 w-3.5" /> Decide
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {queue && queue.total > (queue.page_size ?? 20) && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-surface-100">
            <span className="text-xs text-surface-500">Showing {queueItems.length} of {queue.total}</span>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
              <button className="btn-secondary btn-sm" onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </Card>

      {/* Review Summary Panel */}
      {selectedApp && !decisionModal && (
        <Card className="p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="section-title mb-0">Review Summary</h3>
            <button onClick={() => setSelectedApp(null)} className="btn-ghost btn-sm">Close</button>
          </div>
          {summaryLoading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : summary ? (
            <ReviewSummaryPanel summary={summary} onDecide={() => setDecisionModal(true)} onActivate={() => activateMutation.mutate(selectedApp)} isActivating={activateMutation.isPending} />
          ) : null}
        </Card>
      )}

      {/* Decision Modal */}
      <Modal open={decisionModal} onClose={() => setDecisionModal(false)} title="Make Decision"
        footer={
          <>
            <button className="btn-secondary" onClick={() => setDecisionModal(false)}>Cancel</button>
            <button className="btn-primary" onClick={handleDecide} disabled={decideMutation.isPending}>
              {decideMutation.isPending ? <Spinner size="sm" /> : 'Confirm Decision'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
          <div>
            <label className="label">Action</label>
            <Select value={action} onChange={e => setAction(e.target.value)}>
              <option value="approve">✅ Approve</option>
              <option value="reject">❌ Reject</option>
              <option value="request_more_info">📋 Request More Info</option>
              <option value="escalate">⬆️ Escalate</option>
            </Select>
          </div>
          {action === 'reject' && (
            <div>
              <label className="label">Rejection Reason <span className="text-danger">*</span></label>
              <textarea className="input resize-none" rows={3} value={rejectionReason} onChange={e => setRejectionReason(e.target.value)} placeholder="State the reason for rejection..." />
            </div>
          )}
          <div>
            <label className="label">Notes (optional)</label>
            <textarea className="input resize-none" rows={2} value={notes} onChange={e => setNotes(e.target.value)} placeholder="Additional review notes..." />
          </div>
        </div>
      </Modal>
    </div>
  )
}

function ReviewSummaryPanel({ summary, onDecide, onActivate, isActivating }: {
  summary: ReviewSummary; onDecide: () => void; onActivate: () => void; isActivating: boolean
}) {
  const checks = [
    { label: 'Biometric verified', pass: summary.biometric_verified },
    { label: 'Screening clear', pass: summary.screening_clear },
    { label: 'PEP/IP flagged', pass: !summary.pep_ip_flagged, inverted: true },
    { label: 'EDD required', pass: !summary.edd_required, inverted: true },
  ]
  const allClear = checks.every(c => c.pass)

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
        <div><span className="text-surface-500">Customer</span><br /><span className="font-medium">{summary.customer_name ?? '—'}</span></div>
        <div><span className="text-surface-500">NID</span><br /><span className="font-mono text-xs">{summary.nid_number ?? '—'}</span></div>
        <div><span className="text-surface-500">KYC Type</span><br /><StatusBadge status={summary.kyc_type} /></div>
        <div><span className="text-surface-500">Status</span><br /><StatusBadge status={summary.status} /></div>
        <div><span className="text-surface-500">Risk Score</span><br />
          {summary.risk_score !== null ? (
            <span className="font-semibold">{summary.risk_score} — <StatusBadge status={summary.risk_classification ?? ''} /></span>
          ) : '—'}
        </div>
        <div><span className="text-surface-500">Ref</span><br /><span className="font-mono text-xs">{summary.application_ref}</span></div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {checks.map(c => (
          <div key={c.label} className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${c.pass ? 'bg-success-light text-success-dark' : 'bg-danger-light text-danger-dark'}`}>
            {c.pass ? <CheckCircle2 className="h-4 w-4 flex-shrink-0" /> : <XCircle className="h-4 w-4 flex-shrink-0" />}
            {c.label}
          </div>
        ))}
      </div>

      <div className="flex gap-3">
        {summary.status === 'approved' ? (
          <button onClick={onActivate} className="btn-primary flex-1" disabled={isActivating}>
            {isActivating ? <Spinner size="sm" /> : <><CheckCircle2 className="h-4 w-4" /> Activate Account</>}
          </button>
        ) : (
          <button onClick={onDecide} className="btn-primary flex-1" disabled={!allClear && summary.status !== 'submitted'}>
            <UserCheck className="h-4 w-4" /> Make Decision
          </button>
        )}
      </div>
    </div>
  )
}
