import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, RefreshCw, Mail, MessageSquare, Filter, AlertCircle, CheckCircle } from 'lucide-react'
import { notificationAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, StatusBadge, Spinner, EmptyState, Select, Alert } from '@/components/ui'
import type { NotificationRead } from '@/types/api'

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function maskAddress(address: string): string {
  if (!address) return '—'
  if (address.length <= 4) return '****'
  return address.slice(0, 3) + '****' + address.slice(-2)
}

function ChannelBadge({ channel }: { channel: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
      channel === 'sms' ? 'bg-blue-50 text-blue-600' :
      channel === 'email' ? 'bg-orange-50 text-orange-600' :
      'bg-gray-100 text-gray-600'
    }`}>
      {channel === 'sms' && <MessageSquare className="h-3 w-3" />}
      {channel === 'email' && <Mail className="h-3 w-3" />}
      {channel.toUpperCase()}
    </span>
  )
}

export default function NotificationQueuePage() {
  const qc = useQueryClient()
  const [status, setStatus] = useState('')
  const [channel, setChannel] = useState('')
  const [notifType, setNotifType] = useState('')
  const [page, setPage] = useState(1)
  const [retrying, setRetrying] = useState<string | null>(null)
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['notification-queue', status, channel, notifType, page],
    queryFn: () =>
      notificationAPI.listAll({
        status: status || undefined,
        channel: channel || undefined,
        notification_type: notifType || undefined,
        page,
        page_size: 20,
      }).then(r => r.data),
    refetchInterval: 15_000,
  })

  const retryMutation = useMutation({
    mutationFn: (notifId: string) => notificationAPI.retry(notifId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-queue'] })
      setRetrying(null)
    },
    onError: (err) => {
      setError(getErrorMessage(err))
      setRetrying(null)
    },
  })

  const rows = data?.data ?? []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Bell className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">Notification Queue</h1>
          <p className="text-sm text-surface-500 mt-0.5">All sent and pending notifications with retry controls</p>
        </div>
      </div>

      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

      {/* Filters */}
      <div className="flex gap-3 items-center flex-wrap">
        <Filter className="h-4 w-4 text-surface-400" />
        <Select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }} className="w-36">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="sent">Sent</option>
          <option value="delivered">Delivered</option>
          <option value="failed">Failed</option>
        </Select>
        <Select value={channel} onChange={e => { setChannel(e.target.value); setPage(1) }} className="w-32">
          <option value="">All channels</option>
          <option value="sms">SMS</option>
          <option value="email">Email</option>
        </Select>
        <Select value={notifType} onChange={e => { setNotifType(e.target.value); setPage(1) }} className="w-48">
          <option value="">All types</option>
          <option value="account_activation">Account Activation</option>
          <option value="submission_confirmation">Submission Confirmation</option>
          <option value="approval">Approval</option>
          <option value="rejection">Rejection</option>
          <option value="edd_request">EDD Request</option>
          <option value="kyc_refresh_reminder">KYC Refresh Reminder</option>
          <option value="failed_ekyc">Failed eKYC</option>
        </Select>
        <span className="text-xs text-surface-400 ml-auto">
          {data?.total ?? 0} total
        </span>
      </div>

      {/* Summary counts */}
      {data && !isLoading && (
        <div className="flex gap-4 text-xs">
          {(['pending', 'sent', 'delivered', 'failed'] as const).map(s => {
            const count = rows.filter(r => r.status === s).length
            return (
              <button
                key={s}
                onClick={() => { setStatus(s); setPage(1) }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border transition-colors ${
                  status === s ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-surface-200 text-surface-500 hover:bg-surface-50'
                }`}
              >
                {s === 'failed' && <AlertCircle className="h-3 w-3" />}
                {s === 'delivered' && <CheckCircle className="h-3 w-3" />}
                {s}: {count}
              </button>
            )
          })}
        </div>
      )}

      <Card padding={false}>
        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size="lg" /></div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Bell className="h-12 w-12" />}
            title="No notifications"
            description="No notifications match your current filters"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-100 bg-surface-50">
                  {['Channel', 'Type', 'Recipient', 'Status', 'Retry', 'Sent At', 'Delivered At', 'Actions'].map(h => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-surface-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(n => (
                  <tr key={n.id} className="border-b border-surface-50 hover:bg-surface-50 transition-colors">
                    <td className="px-5 py-3.5"><ChannelBadge channel={n.channel} /></td>
                    <td className="px-5 py-3.5 text-xs text-surface-600 capitalize">
                      {n.notification_type.replace(/_/g, ' ')}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-xs text-surface-500">
                      {maskAddress(n.recipient_address)}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={n.status} />
                    </td>
                    <td className="px-5 py-3.5 text-surface-500 text-xs">{n.retry_count}</td>
                    <td className="px-5 py-3.5 text-surface-400 text-xs">{formatDateTime(n.sent_at)}</td>
                    <td className="px-5 py-3.5 text-surface-400 text-xs">{formatDateTime(n.delivered_at)}</td>
                    <td className="px-5 py-3.5">
                      {n.status === 'failed' && (
                        <button
                          className="btn-secondary btn-sm flex items-center gap-1"
                          disabled={retrying === n.id || retryMutation.isPending}
                          onClick={() => {
                            setRetrying(n.id)
                            retryMutation.mutate(n.id)
                          }}
                        >
                          {retrying === n.id ? <Spinner size="sm" /> : <RefreshCw className="h-3.5 w-3.5" />}
                          Retry
                        </button>
                      )}
                      {n.status !== 'failed' && (
                        <span className="text-xs text-surface-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > 20 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-surface-100">
            <span className="text-xs text-surface-500">
              Showing {rows.length} of {data.total}
            </span>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                Previous
              </button>
              <button className="btn-secondary btn-sm" onClick={() => setPage(p => p + 1)}>
                Next
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}