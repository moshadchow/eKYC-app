import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, CalendarClock, ShieldCheck } from 'lucide-react'
import { lifecycleAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, StatusBadge, Spinner, Alert } from '@/components/ui'
import { useAuthStore } from '@/store/authStore'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function DaysIndicator({ days }: { days: number }) {
  if (days < 0) {
    return <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-danger-light text-danger-dark">Overdue by {Math.abs(days)} days</span>
  }
  const color = days > 30 ? 'text-success' : days >= 8 ? 'text-warning' : 'text-danger'
  const label = days === 0 ? 'Due today' : `${days} days remaining`
  return <span className={`text-sm font-medium ${color}`}>{label}</span>
}

export default function CustomerLifecyclePage() {
  const qc = useQueryClient()
  const storeAccountId = useAuthStore(s => s.accountId)
  const [localAccountId, setLocalAccountId] = useState('')
  const [inputDraft, setInputDraft] = useState('')
  const [initiated, setInitiated] = useState(false)
  const [error, setError] = useState('')

  const accountId = storeAccountId ?? localAccountId

  const { data: schedule, isLoading, isError } = useQuery({
    queryKey: ['lifecycle-schedule', accountId],
    queryFn: () => lifecycleAPI.getSchedule(accountId).then(r => r.data?.data),
    enabled: !!accountId,
    retry: false,
  })

  const initiateMutation = useMutation({
    mutationFn: () => lifecycleAPI.initiate(accountId),
    onSuccess: () => {
      setInitiated(true)
      qc.invalidateQueries({ queryKey: ['lifecycle-schedule', accountId] })
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const canInitiate = schedule && ['scheduled', 'reminder_sent', 'overdue'].includes(schedule.status)
  const isInProgress = schedule?.status === 'in_progress'

  return (
    <div className="p-6 max-w-xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">KYC Status</h1>
          <p className="text-sm text-surface-500 mt-0.5">View and manage your KYC review schedule</p>
        </div>
      </div>

      {!accountId && (
        <Card className="p-6 space-y-4">
          <p className="text-sm text-surface-600">
            Enter your account ID to view your KYC schedule. Your account ID was sent in your activation SMS.
          </p>
          <div>
            <label className="label">Account ID</label>
            <input
              className="input"
              placeholder="e.g. 3f2a1b..."
              value={inputDraft}
              onChange={e => setInputDraft(e.target.value)}
            />
          </div>
          <button
            className="btn-primary"
            disabled={!inputDraft.trim()}
            onClick={() => setLocalAccountId(inputDraft.trim())}
          >
            View Schedule
          </button>
        </Card>
      )}

      {accountId && isLoading && (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      )}

      {accountId && isError && (
        <Alert variant="error">
          No KYC schedule found for this account. Please check your account ID or contact support.
        </Alert>
      )}

      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

      {schedule && (
        <Card className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-surface-500 text-xs uppercase tracking-wide">Risk Tier</span>
              <div className="mt-1"><StatusBadge status={schedule.risk_tier} /></div>
            </div>
            <div>
              <span className="text-surface-500 text-xs uppercase tracking-wide">Status</span>
              <div className="mt-1"><StatusBadge status={schedule.status} /></div>
            </div>
            <div>
              <span className="text-surface-500 text-xs uppercase tracking-wide">Review Due</span>
              <div className="mt-1 flex items-center gap-1.5 text-surface-800 font-medium">
                <CalendarClock className="h-4 w-4 text-surface-400" />
                {formatDate(schedule.due_date)}
              </div>
            </div>
            <div>
              <span className="text-surface-500 text-xs uppercase tracking-wide">Days Remaining</span>
              <div className="mt-1"><DaysIndicator days={schedule.days_remaining} /></div>
            </div>
            {schedule.last_reminder_at && (
              <div className="col-span-2">
                <span className="text-surface-500 text-xs uppercase tracking-wide">Last Reminder</span>
                <div className="mt-1 text-surface-600 text-sm">{formatDate(schedule.last_reminder_at)}</div>
              </div>
            )}
          </div>

          <Alert variant="info">
            If none of your details have changed, a self-declaration via your registered mobile or email is sufficient — no documents required.
          </Alert>

          {initiated || isInProgress ? (
            <Alert variant="success">
              Your KYC refresh has been initiated. An agent will contact you within the review period.
            </Alert>
          ) : canInitiate ? (
            <button
              className="btn-primary w-full"
              onClick={() => initiateMutation.mutate()}
              disabled={initiateMutation.isPending}
            >
              {initiateMutation.isPending ? <Spinner size="sm" /> : (
                <><RefreshCw className="h-4 w-4" /> Start KYC Refresh</>
              )}
            </button>
          ) : schedule.status === 'completed' ? (
            <p className="text-sm text-surface-500 text-center">Your KYC is up to date. No action required.</p>
          ) : null}
        </Card>
      )}
    </div>
  )
}
