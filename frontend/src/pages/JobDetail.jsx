import React, { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  ClockIcon,
  CodeBracketIcon,
  LightBulbIcon,
  BugAntIcon,
  InformationCircleIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import { CheckCircleIcon as CheckCircleSolid } from '@heroicons/react/24/solid'
import { jobsAPI } from '../api/client'
import JobStatusBadge from '../components/JobStatusBadge'
import DiffViewer from '../components/DiffViewer'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function shortSha(sha) {
  return sha ? sha.slice(0, 7) : '—'
}

function timeAgo(dateStr) {
  if (!dateStr) return ''
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now - date) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }) {
  // Backend returns confidence as string: "high", "medium", "low"
  // or as a float 0.0-1.0
  let label, className

  if (typeof confidence === 'string') {
    const lower = confidence.toLowerCase()
    label = confidence.charAt(0).toUpperCase() + confidence.slice(1).toLowerCase()
    className =
      lower === 'high'
        ? 'bg-green-100 text-green-800 ring-green-300'
        : lower === 'medium'
        ? 'bg-yellow-100 text-yellow-800 ring-yellow-300'
        : 'bg-red-100 text-red-800 ring-red-300'
  } else {
    const c = parseFloat(confidence)
    label = c >= 0.75 ? 'High' : c >= 0.45 ? 'Medium' : 'Low'
    className =
      c >= 0.75
        ? 'bg-green-100 text-green-800 ring-green-300'
        : c >= 0.45
        ? 'bg-yellow-100 text-yellow-800 ring-yellow-300'
        : 'bg-red-100 text-red-800 ring-red-300'
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ring-1 ring-inset ${className}`}>
      {label} Confidence
    </span>
  )
}

// ── Error type badge ──────────────────────────────────────────────────────────

const ERROR_TYPE_COLORS = {
  syntax:      'bg-red-100 text-red-700',
  timing:      'bg-orange-100 text-orange-700',
  assertion:   'bg-purple-100 text-purple-700',
  elaboration: 'bg-yellow-100 text-yellow-700',
  simulation:  'bg-blue-100 text-blue-700',
  warning:     'bg-gray-100 text-gray-700',
  fatal:       'bg-red-200 text-red-900 font-bold',
}

function ErrorTypeBadge({ type }) {
  const typeKey = (type || 'unknown').toLowerCase()
  const colorClass = ERROR_TYPE_COLORS[typeKey] || 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colorClass}`}>
      {type || 'unknown'}
    </span>
  )
}

// ── Iteration Timeline ────────────────────────────────────────────────────────

const ITERATION_STATUS_CONFIG = {
  pass:    { color: 'bg-green-500', label: 'Pass', textColor: 'text-green-700' },
  fail:    { color: 'bg-red-500',   label: 'Fail', textColor: 'text-red-700' },
  error:   { color: 'bg-red-500',   label: 'Error', textColor: 'text-red-700' },
  running: { color: 'bg-blue-500',  label: 'Running', textColor: 'text-blue-700' },
  pending: { color: 'bg-gray-300',  label: 'Pending', textColor: 'text-gray-500' },
}

function IterationTimeline({ iterations }) {
  if (!iterations || iterations.length === 0) return null

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Iteration Timeline</h3>
      <div className="flex items-start gap-0">
        {iterations.map((iter, idx) => {
          const cfg = ITERATION_STATUS_CONFIG[iter.outcome?.toLowerCase() || iter.status?.toLowerCase()] ||
                      ITERATION_STATUS_CONFIG.pending
          const isLast = idx === iterations.length - 1

          return (
            <React.Fragment key={idx}>
              <div className="flex flex-col items-center min-w-[80px]">
                {/* Circle */}
                <div className={`w-9 h-9 rounded-full ${cfg.color} flex items-center justify-center text-white text-sm font-bold shadow-sm`}>
                  {iter.iteration_number || idx + 1}
                </div>
                {/* Label */}
                <p className={`mt-1.5 text-xs font-semibold ${cfg.textColor}`}>{cfg.label}</p>
                {/* Duration */}
                {iter.duration_seconds && (
                  <p className="text-xs text-gray-400">{iter.duration_seconds}s</p>
                )}
                {/* Error count */}
                {iter.errors_found !== undefined && (
                  <p className="text-xs text-gray-400">{iter.errors_found} error{iter.errors_found !== 1 ? 's' : ''}</p>
                )}
              </div>
              {!isLast && (
                <div className="flex-1 flex items-center mt-4">
                  <div className="h-0.5 w-full bg-gray-200" />
                  <ChevronRightIcon className="h-3 w-3 text-gray-400 flex-shrink-0 -ml-1.5" />
                </div>
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}

// ── Errors List ───────────────────────────────────────────────────────────────

function ErrorsList({ errors }) {
  const [expanded, setExpanded] = useState(null)

  if (!errors || errors.length === 0) return null

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100 bg-gray-50">
        <div className="flex items-center gap-2">
          <BugAntIcon className="h-4 w-4 text-red-500" />
          <h3 className="text-sm font-semibold text-gray-700">Errors Found</h3>
        </div>
        <span className="text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full ring-1 ring-red-200">
          {errors.length} error{errors.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="divide-y divide-gray-100">
        {errors.map((err, idx) => (
          <div
            key={idx}
            className="px-5 py-3 hover:bg-gray-50 cursor-pointer transition-colors"
            onClick={() => setExpanded(expanded === idx ? null : idx)}
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <ErrorTypeBadge type={err.error_type || err.type} />
                  {(err.file_path || err.file) && (
                    <span className="font-mono text-xs text-gray-500">
                      {err.file_path || err.file}
                      {(err.line_number || err.line) ? `:${err.line_number || err.line}` : ''}
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-700">{err.message || err.raw_line || '—'}</p>
                {expanded === idx && err.context && (
                  <pre className="mt-2 text-xs bg-gray-900 text-gray-300 p-3 rounded-lg overflow-x-auto font-mono">
                    {err.context}
                  </pre>
                )}
              </div>
              <ChevronRightIcon
                className={`h-4 w-4 text-gray-400 flex-shrink-0 mt-0.5 transition-transform ${
                  expanded === idx ? 'rotate-90' : ''
                }`}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Debug Result card ─────────────────────────────────────────────────────────

function DebugResult({ result }) {
  if (!result) return null

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="p-1.5 bg-indigo-50 rounded-lg">
          <LightBulbIcon className="h-4 w-4 text-indigo-600" />
        </div>
        <h3 className="text-sm font-semibold text-gray-700">AI Debug Result</h3>
        {result.confidence !== undefined && (
          <div className="ml-auto">
            <ConfidenceBadge confidence={result.confidence} />
          </div>
        )}
      </div>

      {/* Root cause */}
      {result.root_cause && (
        <div className="mb-4 p-4 bg-indigo-50 border border-indigo-100 rounded-xl">
          <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-1.5">
            Root Cause
          </p>
          <p className="text-sm font-semibold text-indigo-900 leading-relaxed">
            {result.root_cause}
          </p>
        </div>
      )}

      {/* Explanation */}
      {result.explanation && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Explanation
          </p>
          <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
            {result.explanation}
          </p>
        </div>
      )}

      {/* Fix summary */}
      {result.fix_summary && (
        <div className="p-3 bg-green-50 border border-green-100 rounded-lg">
          <p className="text-xs font-semibold text-green-700 mb-1">Fix Summary</p>
          <p className="text-sm text-green-800">{result.fix_summary}</p>
        </div>
      )}
    </div>
  )
}

// ── Action buttons ────────────────────────────────────────────────────────────

function ActionButtons({ job, onApprove, onReject, loading }) {
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  // Show action buttons when the AI result is ready and waiting for human approval
  const debugResult = job.debug_result
  const alreadyActed = !!(debugResult?.approved_at || debugResult?.rejected_at)

  if (job.status !== 'analyzing') return null
  if (alreadyActed) return null
  if (!debugResult?.patch) return null

  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Review Fix</h3>
      <p className="text-sm text-gray-600 mb-4">
        The AI has proposed a fix for the detected errors. Review the diff above and approve or reject it.
      </p>
      <div className="flex gap-3">
        <button
          onClick={onApprove}
          disabled={loading}
          className="btn-success"
        >
          <CheckCircleIcon className="h-4 w-4" />
          Approve &amp; Apply Fix
        </button>
        <button
          onClick={() => setShowRejectModal(true)}
          disabled={loading}
          className="btn-danger"
        >
          <XCircleIcon className="h-4 w-4" />
          Reject
        </button>
      </div>

      {/* Reject modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6">
            <h4 className="text-base font-semibold text-gray-900 mb-2">Reject Fix</h4>
            <p className="text-sm text-gray-600 mb-4">
              Optionally provide a reason for rejection.
            </p>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="The fix looks incorrect because..."
              className="input-field resize-none mb-4"
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowRejectModal(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowRejectModal(false)
                  onReject(rejectReason)
                }}
                disabled={loading}
                className="btn-danger"
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Approved/Rejected state cards ─────────────────────────────────────────────

function ApprovedState({ job }) {
  const dr = job.debug_result
  return (
    <div className="card p-5 border-green-200 bg-green-50">
      <div className="flex items-center gap-2 mb-2">
        <CheckCircleSolid className="h-5 w-5 text-green-600" />
        <h3 className="text-sm font-semibold text-green-800">Fix Approved</h3>
      </div>
      <p className="text-sm text-green-700">
        The fix has been approved and is being applied by the runner.
      </p>
      {dr?.approved_at && (
        <p className="text-xs text-green-600 mt-2">Approved {timeAgo(dr.approved_at)}</p>
      )}
    </div>
  )
}

function RejectedState({ job }) {
  const dr = job.debug_result
  return (
    <div className="card p-5 border-red-200 bg-red-50">
      <div className="flex items-center gap-2 mb-2">
        <XCircleIcon className="h-5 w-5 text-red-600" />
        <h3 className="text-sm font-semibold text-red-800">Fix Rejected</h3>
      </div>
      {dr?.rejected_at && (
        <p className="text-xs text-red-600 mt-2">Rejected {timeAgo(dr.rejected_at)}</p>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function JobDetail() {
  const { id } = useParams()
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  const loadJob = useCallback(async () => {
    setError(null)
    try {
      const res = await jobsAPI.get(id)
      setJob(res.data)
    } catch (err) {
      setError('Failed to load job details.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadJob()
    // Auto-refresh for active jobs
    let interval
    if (job && ['queued', 'running', 'logs_uploaded', 'analyzing'].includes(job.status)) {
      interval = setInterval(loadJob, 5000)
    }
    return () => clearInterval(interval)
  }, [loadJob, job?.status])

  const handleApprove = async () => {
    setActionLoading(true)
    setActionError(null)
    try {
      await jobsAPI.approve(id)
      await loadJob()
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to approve fix.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async (reason) => {
    setActionLoading(true)
    setActionError(null)
    try {
      await jobsAPI.reject(id, reason)
      await loadJob()
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to reject fix.')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="animate-pulse space-y-5">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
          <div className="card p-6 space-y-4">
            <div className="h-5 bg-gray-200 rounded w-1/2" />
            <div className="h-4 bg-gray-100 rounded w-1/3" />
          </div>
          <div className="card p-6 h-32" />
          <div className="card p-6 h-24" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="card p-8 text-center">
          <ExclamationTriangleIcon className="h-10 w-10 text-red-400 mx-auto mb-3" />
          <h2 className="text-base font-semibold text-gray-900 mb-1">{error}</h2>
          <button onClick={loadJob} className="btn-secondary mt-4">
            <ArrowPathIcon className="h-4 w-4" />
            Try Again
          </button>
        </div>
      </div>
    )
  }

  if (!job) return null

  const iterations = job.iterations || []
  const parsedErrors = job.parsed_errors || job.errors || []
  const debugResult = job.debug_result || job.ai_result || null
  // Prefer the AI-proposed patch; fall back to the incoming git diff
  const diff = job.debug_result?.patch || job.git_diff || job.patch_diff || null

  const isActive = ['queued', 'running', 'logs_uploaded', 'analyzing'].includes(job.status)

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      {/* Back + refresh */}
      <div className="flex items-center justify-between">
        <Link
          to={job.project_id ? `/projects/${job.project_id}/jobs` : '/dashboard'}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to Jobs
        </Link>
        <button
          onClick={loadJob}
          className={`p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors ${
            isActive ? 'animate-spin-slow' : ''
          }`}
          title={isActive ? 'Auto-refreshing...' : 'Refresh'}
        >
          <ArrowPathIcon className={`h-4 w-4 ${isActive ? 'text-blue-500' : ''}`} />
        </button>
      </div>

      {/* ── 1. Header card ── */}
      <div className="card p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <h1 className="text-lg font-bold text-gray-900 font-mono">
                Job #{String(job.id).slice(0, 8)}
              </h1>
              <JobStatusBadge status={job.status} size="lg" />
              {isActive && (
                <span className="text-xs text-blue-600 flex items-center gap-1">
                  <ArrowPathIcon className="h-3 w-3 animate-spin" />
                  Auto-refreshing
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Branch */}
              <div className="min-w-0">
                <p className="text-xs text-gray-400 mb-0.5">Branch</p>
                <p className="text-sm font-medium text-gray-800 truncate flex items-center gap-1">
                  <CodeBracketIcon className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                  {job.branch || '—'}
                </p>
              </div>

              {/* Commit SHA */}
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Commit</p>
                <p className="text-sm font-mono text-gray-800">
                  {shortSha(job.commit_sha)}
                </p>
              </div>

              {/* Created */}
              <div>
                <p className="text-xs text-gray-400 mb-0.5 flex items-center gap-1">
                  <ClockIcon className="h-3 w-3" /> Created
                </p>
                <p className="text-sm text-gray-700">{formatDate(job.created_at)}</p>
              </div>

              {/* Completed */}
              <div>
                <p className="text-xs text-gray-400 mb-0.5">Completed</p>
                <p className="text-sm text-gray-700">{formatDate(job.completed_at)}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Project link */}
        {job.project_id && (
          <div className="pt-3 border-t border-gray-100">
            <Link
              to={`/projects/${job.project_id}/jobs`}
              className="text-xs text-blue-600 hover:text-blue-700 font-medium"
            >
              {job.project_name || `Project ${job.project_id}`} &rarr;
            </Link>
          </div>
        )}
      </div>

      {/* ── Action error ── */}
      {actionError && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0" />
          {actionError}
        </div>
      )}

      {/* ── Approved / Rejected state (keyed off debug_result timestamps) ── */}
      {job.debug_result?.approved_at && <ApprovedState job={job} />}
      {job.debug_result?.rejected_at && !job.debug_result?.approved_at && (
        <RejectedState job={job} />
      )}

      {/* ── 2. Iteration Timeline ── */}
      {iterations.length > 0 && <IterationTimeline iterations={iterations} />}

      {/* ── 3. Errors Found ── */}
      {parsedErrors.length > 0 && <ErrorsList errors={parsedErrors} />}

      {/* ── 4. Debug Result ── */}
      {debugResult && <DebugResult result={debugResult} />}

      {/* ── 5. Diff Viewer ── */}
      {diff && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
            <InformationCircleIcon className="h-4 w-4 text-gray-400" />
            Proposed Patch
          </h3>
          <DiffViewer diff={diff} title="AI-generated fix" />
        </div>
      )}

      {/* ── 6. Action buttons ── */}
      {job.status === 'analyzing' && (
        <ActionButtons
          job={job}
          onApprove={handleApprove}
          onReject={handleReject}
          loading={actionLoading}
        />
      )}

      {/* Empty state for jobs with no results yet */}
      {!isActive &&
        !parsedErrors.length &&
        !debugResult &&
        !diff &&
        job.status !== 'approved' &&
        job.status !== 'rejected' && (
          <div className="card p-8 text-center">
            <InformationCircleIcon className="h-8 w-8 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500">
              {job.status === 'failed'
                ? 'This job failed before producing results. Check runner logs for details.'
                : job.status === 'timeout'
                ? 'This job timed out before completing analysis.'
                : 'No analysis results available for this job.'}
            </p>
          </div>
        )}
    </div>
  )
}
