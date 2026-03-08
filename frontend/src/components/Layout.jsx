import React, { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  HomeIcon,
  FolderIcon,
  QueueListIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  Bars3Icon,
  XMarkIcon,
  BeakerIcon,
  ChevronDownIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import { authAPI, projectsAPI } from '../api/client'

function NavItem({ to, icon: Icon, children, end = false, onClick }) {
  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
      >
        <Icon className="h-5 w-5 flex-shrink-0" />
        {children}
      </button>
    )
  }

  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
          isActive
            ? 'bg-blue-600 text-white nav-item-active'
            : 'text-gray-400 hover:text-white hover:bg-white/10'
        }`
      }
    >
      <Icon className="h-5 w-5 flex-shrink-0" />
      {children}
    </NavLink>
  )
}

export default function Layout() {
  const [user, setUser] = useState(null)
  const [projects, setProjects] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [projectsExpanded, setProjectsExpanded] = useState(true)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    // Try to get cached user, then refresh from API
    const cached = localStorage.getItem('user')
    if (cached) {
      try {
        setUser(JSON.parse(cached))
      } catch {
        // ignore
      }
    }
    authAPI
      .getMe()
      .then((res) => {
        setUser(res.data)
        localStorage.setItem('user', JSON.stringify(res.data))
      })
      .catch(() => {})

    projectsAPI
      .list()
      .then((res) => setProjects(res.data || []))
      .catch(() => {})
  }, [])

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  const handleLogout = () => {
    authAPI.logout().catch(() => {})
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  const avatarText = user?.name
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : user?.email?.slice(0, 2).toUpperCase() || '??'

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-5 border-b border-white/10">
        <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <BeakerIcon className="h-5 w-5 text-white" />
        </div>
        <div>
          <span className="text-white font-bold text-base tracking-tight">AutoVerif</span>
          <span className="ml-1 text-blue-400 font-bold text-base">AI</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <NavItem to="/dashboard" icon={HomeIcon} end>
          Dashboard
        </NavItem>

        {/* Projects section */}
        <div className="mt-4">
          <button
            onClick={() => setProjectsExpanded((e) => !e)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wider hover:text-gray-400 transition-colors"
          >
            Projects
            <ChevronDownIcon
              className={`h-3.5 w-3.5 transition-transform ${
                projectsExpanded ? 'rotate-0' : '-rotate-90'
              }`}
            />
          </button>

          {projectsExpanded && (
            <div className="mt-1 space-y-0.5">
              {projects.slice(0, 8).map((project) => (
                <NavLink
                  key={project.id}
                  to={`/projects/${project.id}/jobs`}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors truncate ${
                      isActive
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-400 hover:text-white hover:bg-white/10'
                    }`
                  }
                >
                  <FolderIcon className="h-4 w-4 flex-shrink-0" />
                  <span className="truncate">{project.name}</span>
                </NavLink>
              ))}
              <NavLink
                to="/projects/new"
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-white/10'
                  }`
                }
              >
                <PlusIcon className="h-4 w-4 flex-shrink-0" />
                New Project
              </NavLink>
            </div>
          )}
        </div>

        <div className="mt-4 pt-4 border-t border-white/10 space-y-1">
          <NavItem to="/dashboard" icon={QueueListIcon}>
            All Jobs
          </NavItem>
        </div>
      </nav>

      {/* User section */}
      <div className="border-t border-white/10 px-3 py-3">
        {user && (
          <div className="flex items-center gap-3 px-2 py-2 mb-1">
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.name || user.username}
                className="w-8 h-8 rounded-full flex-shrink-0"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                {avatarText}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {user.name || user.email}
              </p>
              <p className="text-xs text-gray-400 truncate">{user.email}</p>
            </div>
          </div>
        )}
        <NavItem icon={ArrowRightOnRectangleIcon} onClick={handleLogout}>
          Sign Out
        </NavItem>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile sidebar drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-gray-900 transform transition-transform duration-200 ease-in-out lg:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <button
          onClick={() => setSidebarOpen(false)}
          className="absolute top-4 right-4 p-1 text-gray-400 hover:text-white"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>
        <SidebarContent />
      </aside>

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:flex-col w-64 bg-gray-900 flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Main content */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Mobile top bar */}
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100"
          >
            <Bars3Icon className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-blue-600 rounded-md flex items-center justify-center">
              <BeakerIcon className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-gray-900">AutoVerif AI</span>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
