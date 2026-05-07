import React from 'react'
import { clsx } from 'clsx'
import { Loader2, CheckCircle2, AlertCircle, Info, X } from 'lucide-react'

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner({ size = 'md', className }: { size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const s = { sm: 'h-4 w-4', md: 'h-5 w-5', lg: 'h-8 w-8' }[size]
  return <Loader2 className={clsx('animate-spin text-brand-600', s, className)} />
}

// ── Alert ─────────────────────────────────────────────────────────────────────
type AlertVariant = 'success' | 'error' | 'warning' | 'info'
const alertStyles: Record<AlertVariant, { wrap: string; icon: React.ReactNode }> = {
  success: { wrap: 'bg-success-light border-success/30 text-success-dark', icon: <CheckCircle2 className="h-4 w-4 text-success flex-shrink-0 mt-0.5" /> },
  error:   { wrap: 'bg-danger-light border-danger/30 text-danger-dark',   icon: <AlertCircle className="h-4 w-4 text-danger flex-shrink-0 mt-0.5" /> },
  warning: { wrap: 'bg-warning-light border-warning/30 text-warning-dark', icon: <AlertCircle className="h-4 w-4 text-warning flex-shrink-0 mt-0.5" /> },
  info:    { wrap: 'bg-info-light border-info/30 text-info-dark',         icon: <Info className="h-4 w-4 text-info flex-shrink-0 mt-0.5" /> },
}
export function Alert({ variant = 'info', title, children, onDismiss }: { variant?: AlertVariant; title?: string; children: React.ReactNode; onDismiss?: () => void }) {
  const { wrap, icon } = alertStyles[variant]
  return (
    <div className={clsx('flex gap-3 rounded-lg border px-4 py-3 text-sm animate-slide-down', wrap)}>
      {icon}
      <div className="flex-1 min-w-0">
        {title && <div className="font-medium mb-0.5">{title}</div>}
        <div className="leading-relaxed">{children}</div>
      </div>
      {onDismiss && <button onClick={onDismiss} className="flex-shrink-0 opacity-60 hover:opacity-100"><X className="h-4 w-4" /></button>}
    </div>
  )
}

// ── Form Field wrapper ────────────────────────────────────────────────────────
export function Field({ label, required, error, hint, children }: { label: string; required?: boolean; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="label">
        {label}{required && <span className="text-danger ml-0.5">*</span>}
      </label>
      {children}
      {error && <p className="error-msg">{error}</p>}
      {hint && !error && <p className="hint-msg">{hint}</p>}
    </div>
  )
}

// ── Input ─────────────────────────────────────────────────────────────────────
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { error?: boolean }>(
  ({ error, className, ...props }, ref) => (
    <input ref={ref} className={clsx('input', error && 'input-error', className)} {...props} />
  )
)
Input.displayName = 'Input'

// ── Select ────────────────────────────────────────────────────────────────────
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & { error?: boolean }>(
  ({ error, className, children, ...props }, ref) => (
    <select ref={ref} className={clsx('input appearance-none bg-[url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 12 12\'%3E%3Cpath fill=\'%2364748b\' d=\'M6 8L1 3h10z\'/%3E%3C/svg%3E")] bg-no-repeat bg-[right_12px_center]', error && 'input-error', className)} {...props}>
      {children}
    </select>
  )
)
Select.displayName = 'Select'

// ── Textarea ──────────────────────────────────────────────────────────────────
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & { error?: boolean }>(
  ({ error, className, ...props }, ref) => (
    <textarea ref={ref} rows={3} className={clsx('input resize-none', error && 'input-error', className)} {...props} />
  )
)
Textarea.displayName = 'Textarea'

// ── OTP Input ─────────────────────────────────────────────────────────────────
export function OTPInput({ value, onChange, length = 6 }: { value: string; onChange: (v: string) => void; length?: number }) {
  const refs = Array.from({ length }, () => React.createRef<HTMLInputElement>())
  const digits = value.split('').concat(Array(length).fill('')).slice(0, length)

  function handleChange(i: number, v: string) {
    const d = v.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[i] = d
    onChange(next.join(''))
    if (d && i < length - 1) refs[i + 1]?.current?.focus()
  }
  function handleKeyDown(i: number, e: React.KeyboardEvent) {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs[i - 1]?.current?.focus()
  }
  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length)
    onChange(text)
    refs[Math.min(text.length, length - 1)]?.current?.focus()
  }

  return (
    <div className="flex gap-2 justify-center">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={d}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={i === 0 ? handlePaste : undefined}
          className={clsx(
            'w-11 h-13 text-center text-xl font-semibold rounded-lg border-2 transition-all',
            'focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none',
            d ? 'border-brand-400 bg-brand-50' : 'border-surface-200 bg-white'
          )}
        />
      ))}
    </div>
  )
}

// ── Progress Steps ────────────────────────────────────────────────────────────
export function Steps({ steps, current }: { steps: { label: string; key: string }[]; current: number }) {
  return (
    <div className="flex items-center gap-0">
      {steps.map((s, i) => (
        <React.Fragment key={s.key}>
          <div className="flex flex-col items-center">
            <div className={clsx('step-dot', i < current ? 'step-dot-done' : i === current ? 'step-dot-active' : 'step-dot-pending')}>
              {i < current ? <CheckCircle2 className="h-4 w-4" /> : <span>{i + 1}</span>}
            </div>
            <span className={clsx('text-xs mt-1 whitespace-nowrap', i === current ? 'text-brand-600 font-medium' : 'text-surface-400')}>{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={clsx('flex-1 h-px mx-2 mb-4', i < current ? 'bg-success' : 'bg-surface-200')} />
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

// ── Status Badge ──────────────────────────────────────────────────────────────
const statusMap: Record<string, string> = {
  draft: 'badge-gray', submitted: 'badge-blue', screening: 'badge-blue',
  risk_grading: 'badge-yellow', edd_pending: 'badge-yellow',
  pending_approval: 'badge-yellow', approved: 'badge-green',
  rejected: 'badge-red', cancelled: 'badge-red',
  low: 'badge-green', medium: 'badge-yellow', high: 'badge-red',
  clear: 'badge-green', potential_match: 'badge-yellow', confirmed_match: 'badge-red',
  active: 'badge-green', suspended: 'badge-yellow', locked: 'badge-red',
}
export function StatusBadge({ status }: { status: string }) {
  return <span className={clsx('badge', statusMap[status] ?? 'badge-gray')}>{status.replace(/_/g, ' ')}</span>
}

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({ children, className, padding = true }: { children: React.ReactNode; className?: string; padding?: boolean }) {
  return <div className={clsx('card', padding && 'p-6', className)}>{children}</div>
}

// ── Modal ─────────────────────────────────────────────────────────────────────
export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-modal w-full max-w-lg animate-slide-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-100">
          <h2 className="font-semibold text-surface-900">{title}</h2>
          <button onClick={onClose} className="text-surface-400 hover:text-surface-600 transition-colors"><X className="h-5 w-5" /></button>
        </div>
        <div className="px-6 py-5">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-surface-100 bg-surface-50 rounded-b-2xl flex justify-end gap-3">{footer}</div>}
      </div>
    </div>
  )
}

// ── Empty State ───────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, description, action }: { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {icon && <div className="mb-4 text-surface-300">{icon}</div>}
      <h3 className="font-medium text-surface-700 mb-1">{title}</h3>
      {description && <p className="text-sm text-surface-400 mb-4 max-w-xs">{description}</p>}
      {action}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
export function SkeletonCard() {
  return (
    <div className="card p-6 space-y-3">
      <div className="skeleton h-4 w-1/3 rounded" />
      <div className="skeleton h-3 w-full rounded" />
      <div className="skeleton h-3 w-3/4 rounded" />
    </div>
  )
}
