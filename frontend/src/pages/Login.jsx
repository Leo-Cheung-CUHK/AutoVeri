import React, { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { BeakerIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'

// GitHub SVG icon
function GitHubIcon({ className }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        clipRule="evenodd"
      />
    </svg>
  )
}

// GitLab SVG icon
function GitLabIcon({ className }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 01-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 014.82 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0118.6 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.51L23 13.45a.84.84 0 01-.35.94z" />
    </svg>
  )
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isDev = import.meta.env.DEV

  useEffect(() => {
    // If token is in query params (OAuth callback), save and redirect
    const token = searchParams.get('token')
    if (token) {
      localStorage.setItem('token', token)
      navigate('/dashboard', { replace: true })
      return
    }

    // Already logged in
    const existingToken = localStorage.getItem('token')
    if (existingToken) {
      navigate('/dashboard', { replace: true })
    }
  }, [searchParams, navigate])

  const handleGitHubLogin = () => {
    window.location.href = `${API_BASE}/auth/github`
  }

  const handleGitLabLogin = () => {
    window.location.href = `${API_BASE}/auth/gitlab`
  }

  const handleDevLogin = async () => {
    const res = await fetch(`${API_BASE}/auth/dev-token`, { method: 'POST' })
    const data = await res.json()
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-slate-800 to-gray-900 flex items-center justify-center p-4">
      {/* Background grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="relative w-full max-w-md">
        {/* Logo / Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl shadow-lg shadow-blue-900/50 mb-4">
            <BeakerIcon className="h-9 w-9 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            AutoVerif <span className="text-blue-400">AI</span>
          </h1>
          <p className="mt-2 text-gray-400 text-sm">
            Automated hardware verification powered by AI
          </p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl shadow-black/30 p-8">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900">Sign in to continue</h2>
            <p className="text-sm text-gray-500 mt-1">
              Choose your Git provider to authenticate
            </p>
          </div>

          <div className="space-y-3">
            {/* GitHub */}
            <button
              onClick={handleGitHubLogin}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-gray-900 hover:bg-gray-800 text-white font-semibold rounded-xl transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-gray-700 focus:ring-offset-2"
            >
              <GitHubIcon className="h-5 w-5" />
              Sign in with GitHub
            </button>

            {/* GitLab */}
            <button
              onClick={handleGitLabLogin}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-orange-600 hover:bg-orange-700 text-white font-semibold rounded-xl transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2"
            >
              <GitLabIcon className="h-5 w-5" />
              Sign in with GitLab
            </button>
          </div>

          {isDev && (
            <button
              onClick={handleDevLogin}
              className="w-full flex items-center justify-center gap-3 px-4 py-2 mt-3 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl transition-colors text-sm"
            >
              Dev Login (skip OAuth)
            </button>
          )}

          <div className="mt-6 flex items-center gap-2 text-xs text-gray-400">
            <ShieldCheckIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
            <span>
              We only request read access to your repositories. Your credentials are
              never stored.
            </span>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center mt-6 text-xs text-gray-500">
          AutoVerif AI &mdash; Hardware Verification Platform
        </p>
      </div>
    </div>
  )
}
