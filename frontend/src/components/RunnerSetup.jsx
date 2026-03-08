import React, { useState } from 'react'
import {
  CheckIcon,
  DocumentDuplicateIcon,
  CommandLineIcon,
} from '@heroicons/react/24/outline'

function CopyableCommand({ command, label }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback: select text
    }
  }

  return (
    <div className="mt-2">
      {label && <p className="text-xs text-gray-500 mb-1">{label}</p>}
      <div className="flex items-center gap-2 bg-gray-900 rounded-lg px-3 py-2.5">
        <code className="flex-1 font-mono text-sm text-green-400 break-all">
          {command}
        </code>
        <button
          onClick={handleCopy}
          title="Copy to clipboard"
          className="flex-shrink-0 p-1 rounded text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
        >
          {copied ? (
            <CheckIcon className="h-4 w-4 text-green-400" />
          ) : (
            <DocumentDuplicateIcon className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  )
}

const STEPS = [
  {
    number: 1,
    title: 'Install the runner',
    description: 'Install the AutoVerif runner via pip:',
  },
  {
    number: 2,
    title: 'Register with your server',
    description: 'Register the runner using your project token:',
  },
  {
    number: 3,
    title: 'Start the runner',
    description: 'Launch the runner service:',
  },
]

export default function RunnerSetup({ token, serverUrl }) {
  const url = serverUrl || window.location.origin
  const runnerToken = token || '<your-runner-token>'

  const commands = [
    'pip install autoverif-runner',
    `autoverif-runner register --server ${url} --token ${runnerToken}`,
    'autoverif-runner start',
  ]

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="p-2 bg-blue-50 rounded-lg">
          <CommandLineIcon className="h-5 w-5 text-blue-600" />
        </div>
        <div>
          <h3 className="text-base font-semibold text-gray-900">Runner Setup</h3>
          <p className="text-xs text-gray-500">
            Install and register a runner to process simulation jobs
          </p>
        </div>
      </div>

      {token && (
        <div className="mb-5 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-xs font-semibold text-amber-800 mb-1">Runner Token</p>
          <code className="text-sm font-mono text-amber-900 break-all">{token}</code>
          <p className="text-xs text-amber-700 mt-1">
            Keep this token secret. It grants access to submit jobs to your project.
          </p>
        </div>
      )}

      <div className="space-y-5">
        {STEPS.map((step, idx) => (
          <div key={step.number} className="flex gap-4">
            {/* Step indicator */}
            <div className="flex flex-col items-center">
              <div className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-full bg-blue-600 text-white text-xs font-bold">
                {step.number}
              </div>
              {idx < STEPS.length - 1 && (
                <div className="w-px flex-1 mt-1 bg-gray-200" />
              )}
            </div>

            {/* Content */}
            <div className="pb-4 flex-1">
              <p className="text-sm font-semibold text-gray-900">{step.title}</p>
              <p className="text-xs text-gray-500 mt-0.5">{step.description}</p>
              <CopyableCommand command={commands[idx]} />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
        <p className="text-xs text-gray-600">
          <strong>Note:</strong> The runner must have network access to your Git
          repository and the AutoVerif server. It will automatically pick up jobs
          when new commits are pushed.
        </p>
      </div>
    </div>
  )
}
