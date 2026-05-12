import  { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { Shield, AlertTriangle, CheckCircle2, TrendingUp, FileText, Play, ChevronDown, ChevronUp, Upload, ArrowLeft } from 'lucide-react'
import { complianceAPI, adminAPI } from '@/api/services'
import { getErrorMessage } from '@/api/client'
import { Card, Alert, Spinner, StatusBadge, Field, Input, Select, DocumentViewer } from '@/components/ui'
import type { ReviewSummary, PEPCheckRequest, ApplicationDocument } from '@/types/api'

export default function CompliancePage() {
  const { appId } = useParams<{ appId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [error, setError] = useState('')
  const [pepOpen, setPepOpen] = useState(false)
  const [pepForm, setPepForm] = useState({ is_pep: false, is_ip: false, is_family_of_pep: false, is_family_of_ip: false, is_high_official_intl_org: false, match_detail: '' })
  const [eddDocType, setEddDocType] = useState('')
  const [eddFile, setEddFile] = useState<File | null>(null)
  const [eddDocError, setEddDocError] = useState('')
  const [eddDocSuccess, setEddDocSuccess] = useState('')

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

  const { data: summary } = useQuery({
    queryKey: ['review-summary', appId],
    queryFn: () => adminAPI.reviewSummary(appId!).then(r => r.data.data).catch(() => null),
    enabled: !!appId,
  })

  const { data: documents } = useQuery({
    queryKey: ['documents', appId],
    queryFn: () => adminAPI.getDocuments(appId!).then(r => r.data.data ?? []),
    enabled: !!appId,
  })

  useEffect(() => {
    qc.invalidateQueries({ queryKey: ['queue'] })
  }, [qc])

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

  const pepMutation = useMutation({
    mutationFn: (body: PEPCheckRequest) => complianceAPI.pepCheck(appId!, body),
    onSuccess: () => {
      refetchRisk()
      setPepOpen(false)
      setPepForm({ is_pep: false, is_ip: false, is_family_of_pep: false, is_family_of_ip: false, is_high_official_intl_org: false, match_detail: '' })
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  async function sha256(file: File): Promise<string> {
    const buffer = await file.arrayBuffer()
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  }

  const eddUploadMutation = useMutation({
    mutationFn: async ({ docType, file }: { docType: string; file: File }) => {
      const checksum = await sha256(file)
      const storageKey = `edd-docs/${appId}/${eddStatus?.edd_id ?? 'new'}/${docType}-${Date.now()}.pdf`
      return complianceAPI.uploadEDDDocument(appId!, eddStatus!.edd_id, {
        document_type: docType,
        storage_key: storageKey,
        checksum_sha256: checksum,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['edd-status', appId] })
      setEddFile(null)
      setEddDocType('')
      setEddDocSuccess('Document uploaded successfully.')
      setTimeout(() => setEddDocSuccess(''), 3000)
    },
    onError: (err) => setEddDocError(getErrorMessage(err)),
  })

  if (!appId) return <div className="p-6 text-surface-500">No application ID provided</div>

  return (
    <div className="p-6 space-y-6">
      {/* Header + Customer Summary */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <button onClick={() => { qc.invalidateQueries({ queryKey: ['queue'] }); navigate('/agent/queue') }} className="flex items-center gap-1.5 text-sm text-surface-500 hover:text-brand-600 transition-colors mb-2">
            <ArrowLeft className="h-4 w-4" /> Back to Queue
          </button>
          <h1 className="page-title">Compliance & Risk</h1>
          <p className="text-sm text-surface-500 mt-0.5">AML/CFT screening and risk grading</p>
        </div>
      </div>

      {/* Customer Summary Card */}
      {summary && (
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            {summary.application_ref && (
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs bg-surface-100 px-2 py-1 rounded">{summary.application_ref}</span>
              </div>
            )}
            {summary.customer_name && <span className="font-medium text-surface-800">{summary.customer_name}</span>}
            {summary.nid_number && (
              <span className="font-mono text-xs bg-surface-100 px-2 py-1 rounded text-surface-600">
                NID: {summary.nid_number.slice(0,4)}xxxx{summary.nid_number.slice(-4)}
              </span>
            )}
            <div className="flex items-center gap-2 ml-auto">
              <span className={`badge ${summary.nid_number ? 'badge-green' : 'badge-red'}`}>
                NID {summary.nid_number ? 'Validated' : 'Missing'}
              </span>
              <span className={`badge ${summary.biometric_verified ? 'badge-green' : 'badge-red'}`}>
                Biometric {summary.biometric_verified ? 'Verified' : 'Failed'}
              </span>
              {summary.pep_ip_flagged && <span className="badge badge-red">PEP/IP</span>}
            </div>
          </div>
        </Card>
      )}

      {/* Documents Card */}
      {documents && documents.length > 0 && (
        <Card className="p-4">
          <h3 className="section-title mb-3">Documents</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {documents.map((doc: ApplicationDocument) => (
              <div key={doc.id} className="border border-surface-200 rounded-lg p-2 bg-white">
                <DocumentViewer storageKey={doc.storage_key} alt={doc.document_type} className="mb-2" />
                <p className="text-xs text-center capitalize text-surface-600">{doc.document_type.replace(/_/g, ' ')}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

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

      {/* PEP / IP Check */}
      <Card className="p-6">
        <button onClick={() => setPepOpen(o => !o)} className="w-full flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-warning" />
            <h3 className="section-title mb-0">PEP / IP Check</h3>
          </div>
          {pepOpen ? <ChevronUp className="h-4 w-4 text-surface-400" /> : <ChevronDown className="h-4 w-4 text-surface-400" />}
        </button>

        {pepOpen && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { key: 'is_pep', label: 'Politically Exposed Person (PEP)' },
                { key: 'is_ip', label: 'Influential Person (IP)' },
                { key: 'is_family_of_pep', label: 'Family Member of PEP' },
                { key: 'is_family_of_ip', label: 'Family Member of IP' },
                { key: 'is_high_official_intl_org', label: 'High Official / Intl Org' },
              ].map(f => (
                <label key={f.key} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pepForm[f.key as keyof typeof pepForm] as boolean}
                    onChange={e => setPepForm(p => ({ ...p, [f.key]: e.target.checked }))}
                    className="w-4 h-4 rounded border-surface-300 text-brand-600"
                  />
                  {f.label}
                </label>
              ))}
            </div>
            <div>
              <label className="label">Match Detail</label>
              <textarea className="input resize-none" rows={2} value={pepForm.match_detail} onChange={e => setPepForm(p => ({ ...p, match_detail: e.target.value }))} placeholder="Enter details if any matches found..." />
            </div>
            <button
              onClick={() => pepMutation.mutate(pepForm)}
              disabled={pepMutation.isPending}
              className="btn-primary btn-sm"
            >
              {pepMutation.isPending ? <Spinner size="sm" /> : 'Submit PEP/IP Check'}
            </button>
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
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm mb-5">
            <div><span className="text-surface-500">Status</span><br /><StatusBadge status={eddStatus.status} /></div>
            <div><span className="text-surface-500">Trigger</span><br /><span>{eddStatus.trigger_reason?.replace(/_/g, ' ')}</span></div>
            <div><span className="text-surface-500">Days Remaining</span><br />
              <span className={eddStatus.days_remaining < 7 ? 'text-danger font-semibold' : 'text-surface-700'}>{eddStatus.days_remaining} days</span>
            </div>
            <div><span className="text-surface-500">Deadline</span><br /><span>{new Date(eddStatus.deadline_at).toLocaleDateString()}</span></div>
          </div>

          {/* EDD Document Upload */}
          {eddStatus.status === 'in_progress' && (
            <div className="border-t border-surface-100 pt-4">
              <h4 className="text-sm font-medium text-surface-700 mb-3 flex items-center gap-2"><Upload className="h-4 w-4" /> Upload EDD Documents</h4>
              {eddDocSuccess && <Alert variant="success" onDismiss={() => setEddDocSuccess('')}>{eddDocSuccess}</Alert>}
              {eddDocError && <Alert variant="error" onDismiss={() => setEddDocError('')}>{eddDocError}</Alert>}
              <div className="flex gap-3 items-end flex-wrap">
                <div className="flex-1 min-w-40">
                  <label className="label">Document Type</label>
                  <Select value={eddDocType} onChange={e => setEddDocType(e.target.value)}>
                    <option value="">Select type...</option>
                    <option value="bank_statement">Bank Statement</option>
                    <option value="income_proof">Income Proof</option>
                    <option value="source_of_fund_declaration">Source of Fund Declaration</option>
                    <option value="tax_return">Tax Return</option>
                    <option value="business_documents">Business Documents</option>
                    <option value="other">Other</option>
                  </Select>
                </div>
                <div className="flex-1 min-w-40">
                  <label className="label">File</label>
                  <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e => setEddFile(e.target.files?.[0] ?? null)} className="input" />
                </div>
                <button
                  onClick={() => eddFile && eddDocType && eddUploadMutation.mutate({ docType: eddDocType, file: eddFile })}
                  disabled={!eddFile || !eddDocType || eddUploadMutation.isPending}
                  className="btn-primary btn-sm"
                >
                  {eddUploadMutation.isPending ? <Spinner size="sm" /> : 'Upload'}
                </button>
              </div>
              {eddStatus.uploaded_documents && eddStatus.uploaded_documents.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs text-surface-500">Uploaded documents:</p>
                  {eddStatus.uploaded_documents.map((doc, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs bg-surface-50 px-3 py-2 rounded">
                      <FileText className="h-3.5 w-3.5 text-surface-400" />
                      <span className="capitalize">{doc.document_type?.replace(/_/g, ' ')}</span>
                      {doc.checksum_sha256 && <span className="text-surface-400 font-mono">({doc.checksum_sha256.slice(0,12)}...)</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Complete Review */}
      {screening && screening.length > 0 && riskScore && (
        <div className="flex justify-end">
          <button
            onClick={() => { qc.invalidateQueries({ queryKey: ['queue'] }); navigate('/agent/queue') }}
            className="btn-primary"
          >
            Complete Review & Return to Queue
          </button>
        </div>
      )}
    </div>
  )
}
