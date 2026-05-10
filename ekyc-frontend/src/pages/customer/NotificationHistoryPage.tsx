import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, MessageSquare, Bell, CheckCircle, XCircle, Clock, Filter } from 'lucide-react'
import { notificationAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, StatusBadge, Spinner, EmptyState, Select } from '@/components/ui'
import type { NotificationRead } from '@/types/api'

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function ChannelIcon({ channel }: { channel: string }) {
  if (channel === 'sms') return <MessageSquare className="h-4 w-4 text-blue-500" />
  if (channel === 'email') return <Mail className="h-4 w-4 text-orange-500" />
  return <Bell className="h-4 w-4 text-gray-500" />
}

function NotificationStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    pending:    { label: 'Pending',    cls: 'bg-yellow-100 text-yellow-700' },
    sent:       { label: 'Sent',       cls: 'bg-blue-100 text-blue-700' },
    delivered:  { label: 'Delivered',  cls: 'bg-green-100 text-green-700' },
    failed:     { label: 'Failed',     cls: 'bg-red-100 text-red-700' },
  }
  const { label, cls } = map[status] ?? { label: status, cls: 'bg-gray-100 text-gray-700' }
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>{label}</span>
}

function NotificationRow({ notif }: { notif: NotificationRead }) {
  return (
    <div className="border-b border-surface-100 last:border-0 py-4 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <ChannelIcon channel={notif.channel} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-sm font-medium text-surface-800 capitalize">
              {notif.notification_type.replace(/_/g, ' ')}
            </span>
            <NotificationStatusBadge status={notif.status} />
          </div>
          <p className="text-sm text-surface-600 line-clamp-2">{notif.message_body}</p>
          {notif.error_message && (
            <p className="text-xs text-red-600 mt-1">Error: {notif.error_message}</p>
          )}
          <div className="flex items-center gap-4 mt-2 text-xs text-surface-400">
            <span>{formatDateTime(notif.created_at)}</span>
            {notif.sent_at && <span>Sent: {formatDateTime(notif.sent_at)}</span>}
            {notif.delivered_at && <span>Delivered: {formatDateTime(notif.delivered_at)}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

const STATUS_TABS = ['all', 'pending', 'sent', 'delivered', 'failed'] as const

export default function NotificationHistoryPage() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['notifications', statusFilter, page],
    queryFn: () =>
      notificationAPI.listByUser({
        status: statusFilter || undefined,
        page,
        page_size: 20,
      }).then(r => r.data),
    retry: 2,
  })

  const rows = data?.data ?? []
  const total = data?.total ?? 0

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Bell className="h-6 w-6 text-brand-600" />
        <div>
          <h1 className="page-title">My Notifications</h1>
          <p className="text-sm text-surface-500 mt-0.5">History of all notifications sent to you</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-surface-200 overflow-x-auto">
        {STATUS_TABS.map(tab => (
          <button
            key={tab}
            onClick={() => { setStatusFilter(tab === 'all' ? '' : tab); setPage(1) }}
            className={[
              'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              (statusFilter === '' && tab === 'all') || statusFilter === tab
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-surface-500 hover:text-surface-800',
            ].join(' ')}
          >
            {tab === 'all' ? 'All' : (
              <span className="capitalize flex items-center gap-1">
                {tab === 'pending' && <Clock className="h-3.5 w-3.5" />}
                {tab === 'failed' && <XCircle className="h-3.5 w-3.5" />}
                {tab === 'delivered' && <CheckCircle className="h-3.5 w-3.5" />}
                {tab}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading && <div className="flex justify-center py-12"><Spinner size="lg" /></div>}

      {isError && (
        <Card className="p-6 text-center text-sm text-red-600">
          Failed to load notifications. Please try again.
        </Card>
      )}

      {!isLoading && rows.length === 0 && (
        <EmptyState
          icon={<Bell className="h-12 w-12" />}
          title="No notifications"
          description={statusFilter ? `No ${statusFilter} notifications found` : 'You have no notifications yet'}
        />
      )}

      {rows.length > 0 && (
        <Card padding={false} className="divide-y divide-surface-100 px-0">
          <div className="px-5 py-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-surface-500">
                Showing {rows.length} of {total}
              </span>
            </div>
          </div>
          <div className="px-5">
            {rows.map(n => <NotificationRow key={n.id} notif={n} />)}
          </div>

          {total > 20 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-surface-100">
              <span className="text-xs text-surface-500">Page {page} of {Math.ceil(total / 20)}</span>
              <div className="flex gap-2">
                <button className="btn-secondary btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                  Previous
                </button>
                <button
                  className="btn-secondary btn-sm"
                  disabled={page >= Math.ceil(total / 20)}
                  onClick={() => setPage(p => p + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}