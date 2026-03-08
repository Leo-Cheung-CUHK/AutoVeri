import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeftIcon,
  ClipboardDocumentIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  FolderPlusIcon,
} from '@heroicons/react/24/outline'
import { projectsAPI } from '../api/client'
import RunnerSetup from '../components/RunnerSetup'

const DEFAULTS = {
  name: '',
  repo_url: '',
  git_provider: 'github',
  sim_command: 'make sim',
  tb_folder_pattern: 'tb_',
  rtl_folder_pattern: 'rtl_',
  timeout_minutes: 30,
  notification_email: '',
}

function CopyableText({ value, label }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }
  return (
    <div>
      {label && <p className="label">{label}</p>}
      <div className="flex items-center gap-2">
        <code className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm font-mono text-gray-700 break-all">
          {value}
        </code>
        <button onClick={handleCopy} className="btn-secondary px-2.5 py-2 flex-shrink-0">
          {copied ? (
            <CheckIcon className="h-4 w-4 text-green-600" />
          ) : (
            <ClipboardDocumentIcon className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  )
}

export default function ProjectNew() {
  const [form, setForm] = useState(DEFAULTS)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [apiError, setApiError] = useState(null)
  const [created, setCreated] = useState(null) // { id, webhook_url, webhook_secret, runner_token }
  const navigate = useNavigate()

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }))
    setErrors((er) => ({ ...er, [field]: undefined }))
  }

  const validate = () => {
    const errs = {}
    if (!form.name.trim()) errs.name = 'Project name is required'
    if (!form.repo_url.trim()) errs.repo_url = 'Repository URL is required'
    else if (!/^https?:\/\//.test(form.repo_url))
      errs.repo_url = 'Must be a valid URL starting with http(s)://'
    if (!form.sim_command.trim()) errs.sim_command = 'Simulation command is required'
    if (form.timeout_minutes < 1 || form.timeout_minutes > 480)
      errs.timeout_minutes = 'Timeout must be between 1 and 480 minutes'
    return errs
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }
    setSubmitting(true)
    setApiError(null)
    try {
      const payload = {
        ...form,
        timeout_minutes: Number(form.timeout_minutes),
      }
      const res = await projectsAPI.create(payload)
      // webhook_secret doubles as runner registration token
      setCreated({ ...res.data, runner_token: res.data.webhook_secret })
    } catch (err) {
      setApiError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Failed to create project. Please try again.'
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (created) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="mb-6 flex items-center gap-2 text-green-600">
          <CheckIcon className="h-6 w-6" />
          <h1 className="text-xl font-bold text-gray-900">Project Created!</h1>
        </div>

        <div className="card p-6 mb-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Webhook Configuration</h2>
          <p className="text-sm text-gray-600">
            Add this webhook to your repository to trigger verification jobs on push events.
          </p>
          <CopyableText
            value={created.webhook_url || `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/projects/${created.id}/webhook`}
            label="Webhook URL"
          />
          <CopyableText value={created.webhook_secret} label="Webhook Secret" />
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
            <strong>Important:</strong> Copy the webhook secret now. It will not be shown again.
          </div>
        </div>

        <RunnerSetup
          token={created.runner_token}
          serverUrl={window.location.origin}
        />

        <div className="mt-6 flex gap-3">
          <Link to="/dashboard" className="btn-secondary">
            <ArrowLeftIcon className="h-4 w-4" />
            Dashboard
          </Link>
          <Link to={`/projects/${created.id}/jobs`} className="btn-primary">
            View Project Jobs
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/dashboard" className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
          <ArrowLeftIcon className="h-4 w-4" />
        </Link>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
            <FolderPlusIcon className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">New Project</h1>
            <p className="text-xs text-gray-500">Configure a hardware verification project</p>
          </div>
        </div>
      </div>

      {apiError && (
        <div className="mb-5 flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0 mt-0.5" />
          {apiError}
        </div>
      )}

      <form onSubmit={handleSubmit} className="card p-6 space-y-5">
        {/* Project Name */}
        <div>
          <label className="label" htmlFor="name">Project Name *</label>
          <input
            id="name"
            type="text"
            value={form.name}
            onChange={set('name')}
            placeholder="my-soc-verification"
            className={`input-field ${errors.name ? 'border-red-400 focus:border-red-400 focus:ring-red-400' : ''}`}
          />
          {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
        </div>

        {/* Repo URL */}
        <div>
          <label className="label" htmlFor="repo_url">Repository URL *</label>
          <input
            id="repo_url"
            type="url"
            value={form.repo_url}
            onChange={set('repo_url')}
            placeholder="https://github.com/org/repo"
            className={`input-field ${errors.repo_url ? 'border-red-400 focus:border-red-400 focus:ring-red-400' : ''}`}
          />
          {errors.repo_url && <p className="mt-1 text-xs text-red-600">{errors.repo_url}</p>}
        </div>

        {/* Git Provider */}
        <div>
          <label className="label" htmlFor="git_provider">Git Provider</label>
          <select
            id="git_provider"
            value={form.git_provider}
            onChange={set('git_provider')}
            className="input-field"
          >
            <option value="github">GitHub</option>
            <option value="gitlab">GitLab</option>
          </select>
        </div>

        <hr className="border-gray-100" />
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide -mb-2">
          Simulation Settings
        </p>

        {/* Sim Command */}
        <div>
          <label className="label" htmlFor="sim_command">Simulation Command *</label>
          <input
            id="sim_command"
            type="text"
            value={form.sim_command}
            onChange={set('sim_command')}
            placeholder="make sim"
            className={`input-field font-mono ${errors.sim_command ? 'border-red-400' : ''}`}
          />
          {errors.sim_command && (
            <p className="mt-1 text-xs text-red-600">{errors.sim_command}</p>
          )}
          <p className="mt-1 text-xs text-gray-400">
            Command executed by the runner to run your simulation
          </p>
        </div>

        {/* Folder patterns — 2 columns */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="tb_folder">Testbench Folder Pattern</label>
            <input
              id="tb_folder"
              type="text"
              value={form.tb_folder_pattern}
              onChange={set('tb_folder_pattern')}
              placeholder="tb_"
              className="input-field font-mono"
            />
          </div>
          <div>
            <label className="label" htmlFor="rtl_folder">RTL Folder Pattern</label>
            <input
              id="rtl_folder"
              type="text"
              value={form.rtl_folder_pattern}
              onChange={set('rtl_folder_pattern')}
              placeholder="rtl_"
              className="input-field font-mono"
            />
          </div>
        </div>

        {/* Timeout */}
        <div>
          <label className="label" htmlFor="timeout">Timeout (minutes)</label>
          <input
            id="timeout"
            type="number"
            min={1}
            max={480}
            value={form.timeout_minutes}
            onChange={set('timeout_minutes')}
            className={`input-field w-32 ${errors.timeout_minutes ? 'border-red-400' : ''}`}
          />
          {errors.timeout_minutes && (
            <p className="mt-1 text-xs text-red-600">{errors.timeout_minutes}</p>
          )}
        </div>

        <hr className="border-gray-100" />

        {/* Notification email */}
        <div>
          <label className="label" htmlFor="email">Notification Email</label>
          <input
            id="email"
            type="email"
            value={form.notification_email}
            onChange={set('notification_email')}
            placeholder="engineer@company.com (optional)"
            className="input-field"
          />
          <p className="mt-1 text-xs text-gray-400">
            Receive email notifications when jobs complete or fail
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary"
          >
            {submitting ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Creating...
              </>
            ) : (
              'Create Project'
            )}
          </button>
          <Link to="/dashboard" className="btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}
