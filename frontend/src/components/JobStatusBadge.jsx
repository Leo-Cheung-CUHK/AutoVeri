import React from 'react'

const STATUS_CONFIG = {
  queued: {
    label: 'Queued',
    className: 'bg-gray-100 text-gray-700 ring-gray-200',
    dot: 'bg-gray-400',
    pulse: false,
  },
  running: {
    label: 'Running',
    className: 'bg-blue-50 text-blue-700 ring-blue-200',
    dot: 'bg-blue-500',
    pulse: true,
  },
  logs_uploaded: {
    label: 'Logs Uploaded',
    className: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
    dot: 'bg-indigo-500',
    pulse: false,
  },
  analyzing: {
    label: 'Analyzing',
    className: 'bg-purple-50 text-purple-700 ring-purple-200',
    dot: 'bg-purple-500',
    pulse: true,
  },
  completed: {
    label: 'Completed',
    className: 'bg-green-50 text-green-700 ring-green-200',
    dot: 'bg-green-500',
    pulse: false,
  },
  approved: {
    label: 'Approved',
    className: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    dot: 'bg-emerald-500',
    pulse: false,
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-red-50 text-red-700 ring-red-200',
    dot: 'bg-red-500',
    pulse: false,
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-50 text-red-700 ring-red-200',
    dot: 'bg-red-500',
    pulse: false,
  },
  timeout: {
    label: 'Timeout',
    className: 'bg-orange-50 text-orange-700 ring-orange-200',
    dot: 'bg-orange-500',
    pulse: false,
  },
}

export default function JobStatusBadge({ status, size = 'sm' }) {
  const config = STATUS_CONFIG[status] || {
    label: status || 'Unknown',
    className: 'bg-gray-100 text-gray-600 ring-gray-200',
    dot: 'bg-gray-400',
    pulse: false,
  }

  const sizeClass = size === 'lg'
    ? 'px-3 py-1 text-sm gap-2'
    : 'px-2 py-0.5 text-xs gap-1.5'

  const dotSize = size === 'lg' ? 'h-2.5 w-2.5' : 'h-2 w-2'

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ring-1 ring-inset ${config.className} ${sizeClass}`}
    >
      <span className={`relative flex ${dotSize}`}>
        {config.pulse && (
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.dot}`}
          />
        )}
        <span className={`relative inline-flex rounded-full ${dotSize} ${config.dot}`} />
      </span>
      {config.label}
    </span>
  )
}
