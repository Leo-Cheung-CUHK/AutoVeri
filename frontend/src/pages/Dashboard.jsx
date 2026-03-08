import React, { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  FolderIcon,
  PlusIcon,
  ArrowRightIcon,
  ClockIcon,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  QueueListIcon,
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

function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mb-3">
        <Icon className="h-6 w-6 text-gray-400" />
      </div>
      <h3 className="text-sm font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 max-w-xs mb-4">{description}</p>
      {action}
    </div>
  )
}

export default function Dashboard() {
  const [projects, setProjects] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const loadData = useCallback(async () => {
    setError(null)
    setLoadingProjects(true)
    setLoadingJobs(true)
    try {
      const [projRes, jobsRes] = await Promise.all([
        projectsAPI.list(),
        jobsAPI.listAll({ limit: 20, offset: 0 }),
      ])
      setProjects(projRes.data || [])
      setRecentJobs(jobsRes.data?.items || jobsRes.data || [])
    } catch (err) {
      setError('Failed to load data. Please try again.')
    } finally {
      setLoadingProjects(false)
      setLoadingJobs(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Overview of your projects and recent verification jobs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title="Refresh"
          >
            <ArrowPathIcon className="h-4 w-4" />
          </button>
          <Link to="/projects/new" className="btn-primary">
            <PlusIcon className="h-4 w-4" />
            New Project
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0" />
          {error}
          <button onClick={loadData} className="ml-auto underline font-medium">
            Retry
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Projects panel — 2/5 width */}
        <div className="lg:col-span-2">
          <div className="card">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-700">Projects</h2>
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                {projects.length}
              </span>
            </div>

            {loadingProjects ? (
              <div className="divide-y divide-gray-100">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="px-5 py-4 animate-pulse">
                    <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                    <div className="h-3 bg-gray-100 rounded w-1/2" />
                  </div>
                ))}
              </div>
            ) : projects.length === 0 ? (
              <EmptyState
                icon={FolderIcon}
                title="No projects yet"
                description="Create your first project to start verifying hardware designs."
                action={
                  <Link to="/projects/new" className="btn-primary text-xs">
                    <PlusIcon className="h-3.5 w-3.5" />
                    Create Project
                  </Link>
                }
              />
            ) : (
              <div className="divide-y divide-gray-100">
                {projects.map((project) => (
                  <div
                    key={project.id}
                    className="px-5 py-4 hover:bg-gray-50 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex-shrink-0 w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
                          <FolderIcon className="h-4 w-4 text-blue-600" />
                        </div>
                        <div className="min-w-0">
                          <Link
                            to={`/projects/${project.id}/jobs`}
                            className="text-sm font-semibold text-gray-900 hover:text-blue-600 transition-colors truncate block"
                          >
                            {project.name}
                          </Link>
                          <p className="text-xs text-gray-400 truncate mt-0.5">
                            {project.repo_url}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {project.last_job_status && (
                          <JobStatusBadge status={project.last_job_status} />
                        )}
                        <Link
                          to={`/projects/${project.id}/settings`}
                          className="p-1 text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-all rounded"
                          title="Settings"
                        >
                          <Cog6ToothIcon className="h-4 w-4" />
                        </Link>
                      </div>
                    </div>
                    <div className="mt-2 pl-11">
                      <Link
                        to={`/projects/${project.id}/jobs`}
                        className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
                      >
                        View jobs
                        <ArrowRightIcon className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent Jobs panel — 3/5 width */}
        <div className="lg:col-span-3">
          <div className="card">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-700">Recent Jobs</h2>
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                {recentJobs.length}
              </span>
            </div>

            {loadingJobs ? (
              <div className="divide-y divide-gray-100">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="px-5 py-3 animate-pulse flex items-center gap-3">
                    <div className="h-6 bg-gray-200 rounded w-24" />
                    <div className="h-4 bg-gray-100 rounded w-20 ml-auto" />
                    <div className="h-4 bg-gray-100 rounded w-16" />
                  </div>
                ))}
              </div>
            ) : recentJobs.length === 0 ? (
              <EmptyState
                icon={QueueListIcon}
                title="No jobs yet"
                description="Jobs will appear here once your runner processes a commit."
              />
            ) : (
              <div className="divide-y divide-gray-100">
                {recentJobs.map((job) => (
                  <Link
                    key={job.id}
                    to={`/jobs/${job.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors group"
                  >
                    {/* Status */}
                    <JobStatusBadge status={job.status} />

                    {/* Job info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          {shortSha(job.commit_sha)}
                        </span>
                        {job.branch && (
                          <span className="text-xs text-gray-500 truncate max-w-[120px]">
                            {job.branch}
                          </span>
                        )}
                        {job.project_name && (
                          <span className="text-xs text-blue-600 font-medium truncate">
                            {job.project_name}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Time */}
                    <div className="flex items-center gap-1 text-xs text-gray-400 flex-shrink-0">
                      <ClockIcon className="h-3.5 w-3.5" />
                      {timeAgo(job.created_at)}
                    </div>

                    <ArrowRightIcon className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors flex-shrink-0" />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
