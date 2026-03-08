import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeftIcon,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { projectsAPI } from '../api/client'
import RunnerSetup from '../components/RunnerSetup'

export default function ProjectSettings() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    name: '',
    repo_url: '',
    git_provider: 'github',
    sim_command: 'make sim',
    tb_folder_pattern: 'tb_',
    rtl_folder_pattern: 'rtl_',
    timeout_minutes: 30,
    notification_email: '',
  })
  const [runnerToken, setRunnerToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [errors, setErrors] = useState({})
  const [apiError, setApiError] = useState(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  useEffect(() => {
    projectsAPI
      .get(id)
      .then((projRes) => {
        const p = projRes.data
        setForm({
          name: p.name || '',
          repo_url: p.repo_url || '',
          git_provider: p.git_provider || 'github',
          sim_command: p.sim_command || 'make sim',
          tb_folder_pattern: p.tb_folder_pattern || 'tb_',
          rtl_folder_pattern: p.rtl_folder_pattern || 'rtl_',
          timeout_minutes: p.timeout_minutes || 30,
          notification_email: p.notification_email || '',
        })
        // webhook_secret is used as the runner registration token
        setRunnerToken(p.webhook_secret || '')
      })
      .catch(() => setApiError('Failed to load project settings.'))
      .finally(() => setLoading(false))
  }, [id])

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }))
    setErrors((er) => ({ ...er, [field]: undefined }))
    setSaveSuccess(false)
  }

  const validate = () => {
    const errs = {}
    if (!form.name.trim()) errs.name = 'Project name is required'
    if (!form.repo_url.trim()) errs.repo_url = 'Repository URL is required'
    if (!form.sim_command.trim()) errs.sim_command = 'Simulation command is required'
    if (form.timeout_minutes < 1 || form.timeout_minutes > 480)
      errs.timeout_minutes = 'Timeout must be 1–480 minutes'
    return errs
  }

  const handleSave = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setSaving(true)
    setApiError(null)
    try {
      await projectsAPI.update(id, { ...form, timeout_minutes: Number(form.timeout_minutes) })
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err) {
      setApiError(err.response?.data?.detail || 'Failed to save settings.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await projectsAPI.delete(id)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setApiError(err.response?.data?.detail || 'Failed to delete project.')
      setDeleting(false)
      setShowDeleteConfirm(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
          <div className="card p-6 space-y-4">
            {[...Array(6)].map((_, i) => (
              <div key={i}>
                <div className="h-4 bg-gray-200 rounded w-1/4 mb-2" />
                <div className="h-9 bg-gray-100 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link
          to={`/projects/${id}/jobs`}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="h-4 w-4" />
        </Link>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center">
            <Cog6ToothIcon className="h-5 w-5 text-gray-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Project Settings</h1>
            <p className="text-xs text-gray-500">{form.name}</p>
          </div>
        </div>
      </div>

      {apiError && (
        <div className="mb-5 flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0 mt-0.5" />
          {apiError}
        </div>
      )}

      {saveSuccess && (
        <div className="mb-5 flex items-center gap-2 p-4 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
          <CheckIcon className="h-4 w-4" />
          Settings saved successfully.
        </div>
      )}

      <form onSubmit={handleSave} className="card p-6 space-y-5 mb-6">
        {/* Name */}
        <div>
          <label className="label">Project Name *</label>
          <input type="text" value={form.name} onChange={set('name')} className={`input-field ${errors.name ? 'border-red-400' : ''}`} />
          {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
        </div>

        {/* Repo URL */}
        <div>
          <label className="label">Repository URL *</label>
          <input type="url" value={form.repo_url} onChange={set('repo_url')} className={`input-field ${errors.repo_url ? 'border-red-400' : ''}`} />
          {errors.repo_url && <p className="mt-1 text-xs text-red-600">{errors.repo_url}</p>}
        </div>

        {/* Git Provider */}
        <div>
          <label className="label">Git Provider</label>
          <select value={form.git_provider} onChange={set('git_provider')} className="input-field">
            <option value="github">GitHub</option>
            <option value="gitlab">GitLab</option>
          </select>
        </div>

        <hr className="border-gray-100" />
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide -mb-2">Simulation Settings</p>

        {/* Sim command */}
        <div>
          <label className="label">Simulation Command *</label>
          <input type="text" value={form.sim_command} onChange={set('sim_command')} className={`input-field font-mono ${errors.sim_command ? 'border-red-400' : ''}`} />
          {errors.sim_command && <p className="mt-1 text-xs text-red-600">{errors.sim_command}</p>}
        </div>

        {/* Folder patterns */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Testbench Folder Pattern</label>
            <input type="text" value={form.tb_folder_pattern} onChange={set('tb_folder_pattern')} className="input-field font-mono" />
          </div>
          <div>
            <label className="label">RTL Folder Pattern</label>
            <input type="text" value={form.rtl_folder_pattern} onChange={set('rtl_folder_pattern')} className="input-field font-mono" />
          </div>
        </div>

        {/* Timeout */}
        <div>
          <label className="label">Timeout (minutes)</label>
          <input type="number" min={1} max={480} value={form.timeout_minutes} onChange={set('timeout_minutes')} className={`input-field w-32 ${errors.timeout_minutes ? 'border-red-400' : ''}`} />
          {errors.timeout_minutes && <p className="mt-1 text-xs text-red-600">{errors.timeout_minutes}</p>}
        </div>

        <hr className="border-gray-100" />

        {/* Email */}
        <div>
          <label className="label">Notification Email</label>
          <input type="email" value={form.notification_email} onChange={set('notification_email')} placeholder="engineer@company.com" className="input-field" />
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Saving...
              </>
            ) : 'Save Settings'}
          </button>
          <Link to={`/projects/${id}/jobs`} className="btn-secondary">
            Cancel
          </Link>
        </div>
      </form>

      {/* Runner setup */}
      {runnerToken && (
        <div className="mb-6">
          <RunnerSetup token={runnerToken} serverUrl={window.location.origin} />
        </div>
      )}

      {/* Danger zone */}
      <div className="card p-6 border-red-200">
        <h3 className="text-sm font-semibold text-red-700 mb-1">Danger Zone</h3>
        <p className="text-sm text-gray-600 mb-4">
          Deleting this project will permanently remove all jobs, logs, and results. This action cannot be undone.
        </p>
        {!showDeleteConfirm ? (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="btn-danger"
          >
            <TrashIcon className="h-4 w-4" />
            Delete Project
          </button>
        ) : (
          <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-700 flex-1">
              Are you sure? All data will be permanently deleted.
            </p>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="btn-danger text-xs"
            >
              {deleting ? 'Deleting...' : 'Yes, Delete'}
            </button>
            <button
              onClick={() => setShowDeleteConfirm(false)}
              className="btn-secondary text-xs"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
