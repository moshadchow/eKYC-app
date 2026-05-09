import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Shield, AlertTriangle, CheckCircle2, TrendingUp, FileText, Play } from 'lucide-react'
import { complianceAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, Alert, Spinner, StatusBadge, Field, Input, Select } from '@/components/ui'

export default function CompliancePage() {
  const { appId } = useParams<{ appId: string }>()
  const qc = useQueryClient()
  const [error, setError] = useState('')

  const { data: screening, refetch: refetchScreening, isFetching: screeningLoading } = useQuery({
    queryKey: ['screening', appId],
    queryFn: () => complianceAPI.getScreening(appId!).then(r => r.data.data ?? []),
    enabled: !!appId,
  })

  const { data: riskScore, refetch: refetchRisk, isFetching: riskLoading } = useQuery({
    queryKey: ['risk-score', appId],
    queryFn: () => complianceAPI.getRisk(appId!).then(r => r.data.data).catch(() => null),
    enabled: !!appId,
  })

  const { data: eddStatus } = useQuery({
    queryKey: ['edd-status', appId],
    queryFn: () => complianceAPI.getEDDStatus(appId!).then(r => r.data.data).catch(() => null),
    enabled: !!appId,
  })

  const runScreeningMutation = useMutation({
    mutationFn: () => complianceAPI.runScreening(appId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['screening', appId] }); refetchScreening() },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const calcRiskMutation = useMutation({
    mutationFn: () => complianceAPI.calculateRisk(appId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['risk-score', appId] }); refetchRisk() },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const eddMutation = useMutation({
    mutationFn: (trigger: string) => complianceAPI.createEDD(appId!, trigger),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['edd-status', appId] }),
    onError: (err) => setError(getErrorMessage(err)),
  })

  if (!appId) return <div className="p-6 text-surface-500">No application ID provided</div>

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="page-title">Compliance & Risk</h1>
        <p className="text-sm text-surface-500 mt-0.5">AML/CFT screening and risk grading</p>
      </div>

      {error && <Alert variant="error" onDismiss={() => setError('')}>{error}</Alert>}

      {/* Screening */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-brand-600" />
            <h3 className="section-title mb-0">Sanctions Screening</h3>
          </div>
          <button onClick={() => runScreeningMutation.mutate()} className="btn-primary btn-sm" disabled={runScreeningMutation.isPending}>
            {runScreeningMutation.isPending ? <Spinner size="sm" /> : <><Play className="h-3.5 w-3.5" /> Run Screening</>}
          </button>
        </div>

        {screeningLoading ? (
          <div className="flex justify-center py-6"><Spinner /></div>
        ) : screening && screening.length > 0 ? (
          <div className="space-y-3">
            {screening.map((r, i) => (
              <div key={i} className={`flex items-center justify-between p-4 rounded-xl border ${r.requires_review ? 'border-warning/30 bg-warning-light' : 'border-success/30 bg-success-light'}`}>
                <div>
                  <div className="font-medium text-sm">{r.list_source}</div>
                  <div className="text-xs text-surface-500 mt-0.5">{r.screen_type?.replace(/_/g, ' ')}</div>
                </div>
                <div className="text-right">
                  <StatusBadge status={r.result} />
                  {r.match_score && <div className="text-xs text-surface-500 mt-1">Score: {(r.match_score * 100).toFixed(0)}%</div>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-surface-400">
            <Shield className="h-10 w-10 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No screening results yet. Click "Run Screening" to start.</p>
          </div>
        )}
      </Card>

      {/* Risk Score */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-brand-600" />
            <h3 className="section-title mb-0">Risk Grading</h3>
          </div>
          <button onClick={() => calcRiskMutation.mutate()} className="btn-primary btn-sm" disabled={calcRiskMutation.isPending}>
            {calcRiskMutation.isPending ? <Spinner size="sm" /> : <><Play className="h-3.5 w-3.5" /> Calculate</>}
          </button>
        </div>

        {riskScore ? (
          <div className="space-y-5">
            {/* Score summary */}
            <div className="flex items-center gap-6 bg-surface-50 rounded-xl p-5">
              <div className="text-center">
                <div className={`text-4xl font-bold ${riskScore.total_score >= 15 ? 'text-danger' : riskScore.total_score >= 8 ? 'text-warning' : 'text-success'}`}>
                  {riskScore.total_score}
                </div>
                <div className="text-xs text-surface-500 mt-1">Total Score</div>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <StatusBadge status={riskScore.risk_classification} />
                  {riskScore.edd_required && <span className="badge badge-red">EDD Required</span>}
                </div>
                <div className="w-full bg-surface-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${riskScore.total_score >= 15 ? 'bg-danger' : riskScore.total_score >= 8 ? 'bg-warning' : 'bg-success'}`}
                    style={{ width: `${Math.min(100, (riskScore.total_score / 20) * 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-surface-400 mt-1"><span>Low (≤7)</span><span>Medium (8–14)</span><span>High (≥15)</span></div>
              </div>
            </div>

            {/* Score breakdown */}
            <div>
              <p className="text-xs font-medium text-surface-500 uppercase tracking-wide mb-3">Score Breakdown</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {riskScore.score_breakdown && Object.entries(riskScore.score_breakdown).map(([k, v]) => (
                  <div key={k} className="bg-surface-50 rounded-lg p-3 text-center">
                    <div className="text-lg font-semibold text-surface-800">{v as number}</div>
                    <div className="text-xs text-surface-500 mt-0.5 capitalize">{k.replace(/_/g, ' ')}</div>
                    {k === 'score_profession' && riskScore.matched_profession_category && (
                      <div className="text-xs text-brand-500 mt-0.5 italic">{riskScore.matched_profession_category.replace(/_/g, ' ')}</div>
                    )}
                    {k === 'score_business_activity' && riskScore.matched_business_category && (
                      <div className="text-xs text-brand-500 mt-0.5 italic">{riskScore.matched_business_category.replace(/_/g, ' ')}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* EDD trigger */}
            {riskScore.edd_required && !eddStatus && (
              <Alert variant="warning" title="Enhanced Due Diligence Required">
                This customer is high-risk. Please create an EDD request.
                <button onClick={() => eddMutation.mutate('high_risk_score')} className="btn-danger btn-sm mt-3 block" disabled={eddMutation.isPending}>
                  {eddMutation.isPending ? <Spinner size="sm" /> : 'Create EDD Request'}
                </button>
              </Alert>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-surface-400">
            <TrendingUp className="h-10 w-10 mx-auto mb-2 opacity-30" />
            <p className="text-sm">Risk score not calculated yet.</p>
          </div>
        )}
      </Card>

      {/* EDD Status */}
      {eddStatus && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <FileText className="h-5 w-5 text-warning" />
            <h3 className="section-title mb-0">EDD Request</h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div><span className="text-surface-500">Status</span><br /><StatusBadge status={eddStatus.status} /></div>
            <div><span className="text-surface-500">Trigger</span><br /><span>{eddStatus.trigger_reason?.replace(/_/g, ' ')}</span></div>
            <div><span className="text-surface-500">Days Remaining</span><br />
              <span className={eddStatus.days_remaining < 7 ? 'text-danger font-semibold' : 'text-surface-700'}>{eddStatus.days_remaining} days</span>
            </div>
            <div><span className="text-surface-500">Deadline</span><br /><span>{new Date(eddStatus.deadline_at).toLocaleDateString()}</span></div>
          </div>
        </Card>
      )}
    </div>
  )
}
