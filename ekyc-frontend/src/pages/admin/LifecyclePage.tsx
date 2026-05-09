import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, AlertTriangle, CheckCircle2, Clock, Filter } from 'lucide-react'
import { lifecycleAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, StatusBadge, Spinner, Modal, Select, EmptyState, Alert } from '@/components/ui'
import type { ScheduleListItem } from '@/types/api'

function daysColor(days: number): string {
  if (days < 0) return 'text-danger font-semibold'
  if (days <= 30) return 'text-warning font-medium'
  return 'text-success'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

// ── Complete Refresh Modal ────────────────────────────────────────────────────

function CompleteRefreshModal({
  open, accountId, onClose, onSuccess,
}: {
  open: boolean; accountId: string; onClose: () => void; onSuccess: () => void
}) {
  const qc = useQueryClient()
  const [tier, setTier] = useState('')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: () => lifecycleAPI.complete(accountId, tier || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lifecycle-overdue'] })
      qc.invalidateQueries({ queryKey: ['lifecycle-all'] })
      setTier('')
      setError('')
      onSuccess()
      onClose()
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Complete KYC Refresh"
      footer={
        <>
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? <Spinner size="sm" /> : 'Confirm'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
        <div>
          <label className="label">New Risk Tier <span className="text-surface-400 text-xs">(optional — keeps current if blank)</span></label>
          <Select value={tier} onChange={e => setTier(e.target.value)}>
            <option value="">Keep current tier</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </Select>
        </div>
        <p className="text-xs text-surface-500">
          The next review date will be set automatically based on the risk tier:
          high = 1 year, medium = 2 years, low = 5 years.
        </p>
      </div>
    </Modal>
  )
}

// ── Overdue Tab ───────────────────────────────────────────────────────────────

function OverdueTab() {
  const qc = useQueryClient()
  const [error, setError] = useState('')
  const [completeTarget, setCompleteTarget] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['lifecycle-overdue'],
    queryFn: () => lifecycleAPI.overdue().then(r => r.data?.data ?? []),
    refetchInterval: 30_000,
  })

  const reminderMutation = useMutation({
    mutationFn: (accountId: string) => lifecycleAPI.sendReminder(accountId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lifecycle-overdue'] }),
    onError: (err) => setError(getErrorMessage(err)),
  })

  const rows = data ?? []

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}
      <Card padding={false}>
        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<CheckCircle2 className="h-12 w-12" />}
            title="No overdue accounts"
            description="All KYC schedules are up to date"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-100 bg-surface-50">
                  {['Account ID', 'Risk Tier', 'Due Date', 'Days Overdue', 'Reminders', 'Actions'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-surface-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s: ScheduleListItem) => (
                  <tr key={s.schedule_id} className="border-b border-surface-50 hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-xs text-surface-600">{s.account_id.slice(-8)}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={s.risk_tier} /></td>
                    <td className="px-5 py-3.5 text-surface-600 text-xs">{formatDate(s.due_date)}</td>
                    <td className="px-5 py-3.5 text-danger font-semibold">{Math.abs(s.days_remaining)}d overdue</td>
                    <td className="px-5 py-3.5 text-surface-600">{s.reminder_count}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex gap-2">
                        <button
                          className="btn-secondary btn-sm"
                          disabled={reminderMutation.isPending}
                          onClick={() => reminderMutation.mutate(s.account_id)}
                        >
                          {reminderMutation.isPending ? <Spinner size="sm" /> : 'Send Reminder'}
                        </button>
                        <button
                          className="btn-primary btn-sm"
                          onClick={() => setCompleteTarget(s.account_id)}
                        >
                          Complete Refresh
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {completeTarget && (
        <CompleteRefreshModal
          open={!!completeTarget}
          accountId={completeTarget}
          onClose={() => setCompleteTarget(null)}
          onSuccess={() => setCompleteTarget(null)}
        />
      )}
    </div>
  )
}

// ── All Schedules Tab ─────────────────────────────────────────────────────────

function AllSchedulesTab() {
  const qc = useQueryClient()
  const [riskTier, setRiskTier] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')
  const [completeTarget, setCompleteTarget] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['lifecycle-all', riskTier, statusFilter, page],
    queryFn: () => lifecycleAPI.listAll({
      risk_tier: riskTier || undefined,
      status: statusFilter || undefined,
      page,
    }).then(r => r.data),
    refetchInterval: 60_000,
  })

  const reminderMutation = useMutation({
    mutationFn: (accountId: string) => lifecycleAPI.sendReminder(accountId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lifecycle-all'] }),
    onError: (err) => setError(getErrorMessage(err)),
  })

  const rows = data?.data ?? []

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

      <div className="flex gap-3 items-center">
        <Filter className="h-4 w-4 text-surface-400" />
        <Select value={riskTier} onChange={e => { setRiskTier(e.target.value); setPage(1) }} className="w-40">
          <option value="">All risk tiers</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </Select>
        <Select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="w-44">
          <option value="">All statuses</option>
          <option value="scheduled">Scheduled</option>
          <option value="reminder_sent">Reminder Sent</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
          <option value="overdue">Overdue</option>
        </Select>
      </div>

      <Card padding={false}>
        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Clock className="h-12 w-12" />}
            title="No schedules found"
            description="Adjust your filters or check back later"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-100 bg-surface-50">
                  {['Account ID', 'Risk Tier', 'Due Date', 'Days Remaining', 'Status', 'Reminders', 'Actions'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-surface-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s: ScheduleListItem) => (
                  <tr key={s.schedule_id} className="border-b border-surface-50 hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-xs text-surface-600">{s.account_id.slice(-8)}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={s.risk_tier} /></td>
                    <td className="px-5 py-3.5 text-surface-600 text-xs">{formatDate(s.due_date)}</td>
                    <td className={`px-5 py-3.5 text-sm ${daysColor(s.days_remaining)}`}>
                      {s.days_remaining < 0 ? `${Math.abs(s.days_remaining)}d overdue` : `${s.days_remaining}d`}
                    </td>
                    <td className="px-5 py-3.5"><StatusBadge status={s.status} /></td>
                    <td className="px-5 py-3.5 text-surface-600">{s.reminder_count}</td>
                    <td className="px-5 py-3.5">
                      {s.status !== 'completed' && (
                        <div className="flex gap-2">
                          <button
                            className="btn-secondary btn-sm"
                            disabled={reminderMutation.isPending}
                            onClick={() => reminderMutation.mutate(s.account_id)}
                          >
                            Send Reminder
                          </button>
                          <button
                            className="btn-primary btn-sm"
                            onClick={() => setCompleteTarget(s.account_id)}
                          >
                            Complete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > (data.page_size ?? 20) && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-surface-100">
            <span className="text-xs text-surface-500">Showing {rows.length} of {data.total}</span>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
              <button className="btn-secondary btn-sm" onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </Card>

      {completeTarget && (
        <CompleteRefreshModal
          open={!!completeTarget}
          accountId={completeTarget}
          onClose={() => setCompleteTarget(null)}
          onSuccess={() => setCompleteTarget(null)}
        />
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LifecyclePage() {
  const [activeTab, setActiveTab] = useState<'overdue' | 'all'>('overdue')

  const tabs = [
    { key: 'overdue' as const, label: 'Overdue', icon: <AlertTriangle className="h-4 w-4" /> },
    { key: 'all' as const, label: 'All Schedules', icon: <Clock className="h-4 w-4" /> },
  ]

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <RefreshCw className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">KYC Lifecycle</h1>
          <p className="text-sm text-surface-500 mt-0.5">Manage periodic KYC refresh schedules</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-surface-200">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={[
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === tab.key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-surface-500 hover:text-surface-800',
            ].join(' ')}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overdue' ? <OverdueTab /> : <AllSchedulesTab />}
    </div>
  )
}
