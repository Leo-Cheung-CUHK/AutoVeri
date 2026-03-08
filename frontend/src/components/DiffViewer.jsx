import React, { useMemo } from 'react'
import { DocumentDuplicateIcon, CheckIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

function classifyLine(line) {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'add'
  if (line.startsWith('-') && !line.startsWith('---')) return 'remove'
  if (line.startsWith('@@')) return 'hunk'
  if (line.startsWith('+++') || line.startsWith('---')) return 'file'
  if (line.startsWith('diff ') || line.startsWith('index ')) return 'meta'
  return 'context'
}

const LINE_CLASSES = {
  add: 'bg-green-950 text-green-300 border-l-2 border-green-500',
  remove: 'bg-red-950 text-red-300 border-l-2 border-red-500',
  hunk: 'bg-blue-950 text-blue-300 border-l-2 border-blue-500',
  file: 'bg-gray-700 text-gray-200 border-l-2 border-gray-500 font-semibold',
  meta: 'bg-gray-800 text-gray-400 border-l-2 border-gray-600',
  context: 'text-gray-300',
}

export default function DiffViewer({ diff, title = 'Patch Diff', maxHeight = '480px' }) {
  const [copied, setCopied] = useState(false)

  const lines = useMemo(() => {
    if (!diff) return []
    return diff.split('\n').map((line, idx) => ({
      id: idx,
      text: line,
      type: classifyLine(line),
    }))
  }, [diff])

  const stats = useMemo(() => {
    const additions = lines.filter((l) => l.type === 'add').length
    const deletions = lines.filter((l) => l.type === 'remove').length
    return { additions, deletions }
  }, [lines])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(diff || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard not available
    }
  }

  if (!diff) {
    return (
      <div className="card p-6 text-center text-gray-500 text-sm">
        No diff available for this job.
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-700">{title}</span>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-green-600 font-mono font-semibold">
              +{stats.additions}
            </span>
            <span className="text-red-600 font-mono font-semibold">
              -{stats.deletions}
            </span>
          </div>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-200 transition-colors"
        >
          {copied ? (
            <>
              <CheckIcon className="h-3.5 w-3.5 text-green-600" />
              <span className="text-green-600">Copied</span>
            </>
          ) : (
            <>
              <DocumentDuplicateIcon className="h-3.5 w-3.5" />
              Copy patch
            </>
          )}
        </button>
      </div>

      {/* Diff body */}
      <div
        className="diff-container overflow-auto bg-gray-900"
        style={{ maxHeight }}
      >
        <table className="w-full border-collapse font-mono text-xs leading-5">
          <tbody>
            {lines.map((line) => (
              <tr key={line.id} className={`${LINE_CLASSES[line.type]}`}>
                {/* Line number */}
                <td className="select-none text-gray-600 text-right px-3 py-0 w-12 border-r border-gray-700 bg-gray-900 bg-opacity-50">
                  {line.type !== 'hunk' && line.type !== 'meta' && line.type !== 'file'
                    ? line.id + 1
                    : ''}
                </td>
                {/* Content */}
                <td className="px-3 py-0 whitespace-pre">
                  {line.text || '\u00a0'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
