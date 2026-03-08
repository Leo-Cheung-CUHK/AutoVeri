import React, { useState, useEffect, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeftIcon,
  Cog6ToothIcon,
  ArrowPathIcon,
  QueueListIcon,
  ExclamationTriangleIcon,
  ChevronRightIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline'
import { projectsAPI, jobsAPI } from '../api/client'
import JobStatusBadge from '../components/JobStatusBadge'

function timeAgo(dateStr) {
  if (!dateStr) return '—'
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now - date) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function shortSha(sha) {
  return sha ? sha.slice(0, 7) : '—'
}

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'analyzing', label: 'Analyzing' },
  { value: 'completed', label: 'Completed' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'failed', label: 'Failed' },
  { value: 'timeout', label: 'Timeout' },
]

export default function JobList() {
  const { id: projectId } = useParams()
  const navigate = useNavigate()

  const [project, setProject] = useState(null)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const PAGE_SIZE = 20

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [projRes, jobsRes] = await Promise.all([
        projectsAPI.get(projectId),
        jobsAPI.listByProject(projectId, {
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          status: statusFilter || undefined,
        }),
      ])
      setProject(projRes.data)
      const data = jobsRes.data
      if (Array.isArray(data)) {
        setJobs(data)
        setTotal(data.length)
      } else {
        setJobs(data.items || [])
        setTotal(data.total || (data.items || []).length)
      }
    } catch (err) {
      setError('Failed to load jobs.')
    } finally {
      setLoading(false)
    }
  }, [projectId, page, statusFilter])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Reset page when filter changes
  useEffect(() => {
    setPage(0)
  }, [statusFilter])

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Link
            to="/dashboard"
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeftIcon className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {project?.name || 'Project Jobs'}
            </h1>
            {project?.repo_url && (
              <a
                href={project.repo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline"
              >
                {project.repo_url}
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title="Refresh"
          >
            <ArrowPathIcon className="h-4 w-4" />
          </button>
          <Link
            to={`/projects/${projectId}/settings`}
            className="btn-secondary"
          >
            <Cog6ToothIcon className="h-4 w-4" />
            Settings
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-5 flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0" />
          {error}
          <button onClick={loadData} className="ml-auto underline font-medium">Retry</button>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-4">
        <FunnelIcon className="h-4 w-4 text-gray-400" />
        <div className="flex gap-2 flex-wrap">
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatusFilter(opt.value)}
              className={`px-3 py-1 text-xs font-medium rounded-full border transition-colors ${
                statusFilter === opt.value
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-gray-400">{total} job{total !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="divide-y divide-gray-100">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="px-5 py-4 animate-pulse flex items-center gap-4">
                <div className="h-5 bg-gray-200 rounded w-20" />
                <div className="h-4 bg-gray-100 rounded w-16" />
                <div className="h-4 bg-gray-100 rounded w-24 ml-auto" />
              </div>
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mb-3">
              <QueueListIcon className="h-6 w-6 text-gray-400" />
            </div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">No jobs found</h3>
            <p className="text-sm text-gray-500 max-w-xs">
              {statusFilter
                ? 'No jobs match the selected filter.'
                : 'Jobs will appear here when your runner processes commits.'}
            </p>
          </div>
        ) : (
          <>
            {/* Table header */}
            <div className="hidden sm:grid grid-cols-12 px-5 py-2.5 bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              <div className="col-span-2">Job ID</div>
              <div className="col-span-3">Branch</div>
              <div className="col-span-2">Commit</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Created</div>
              <div className="col-span-1 text-right">View</div>
            </div>

            <div className="divide-y divide-gray-100">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  onClick={() => navigate(`/jobs/${job.id}`)}
                  className="grid grid-cols-12 items-center px-5 py-3.5 hover:bg-gray-50 transition-colors cursor-pointer group"
                >
                  {/* Job ID */}
                  <div className="col-span-2">
                    <span className="font-mono text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded">
                      {String(job.id).slice(0, 8)}
                    </span>
                  </div>

                  {/* Branch */}
                  <div className="col-span-3 truncate">
                    <span className="text-sm text-gray-700 truncate block pr-2">
                      {job.branch || '—'}
                    </span>
                  </div>

                  {/* Commit SHA */}
                  <div className="col-span-2">
                    <span className="font-mono text-xs text-gray-500">
                      {shortSha(job.commit_sha)}
                    </span>
                  </div>

                  {/* Status */}
                  <div className="col-span-2">
                    <JobStatusBadge status={job.status} />
                  </div>

                  {/* Created */}
                  <div className="col-span-2 text-xs text-gray-400">
                    {timeAgo(job.created_at)}
                  </div>

                  {/* Arrow */}
                  <div className="col-span-1 flex justify-end">
                    <ChevronRightIcon className="h-4 w-4 text-gray-300 group-hover:text-gray-500 transition-colors" />
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between mt-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="btn-secondary text-xs disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={(page + 1) * PAGE_SIZE >= total}
            className="btn-secondary text-xs disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
