/**
 * DslViewerModal - Shows the raw OpenSearch DSL JSON body for a query that
 * the retriever sent to the cluster. Used by the eye-icon triggers on the
 * hybrid query, BM25 baseline query, and quality-gate retry cards.
 *
 * The body is shown verbatim except for embedding vectors, which are
 * replaced upstream with a placeholder string for readability.
 */

import { useEffect, useRef, useState } from 'react'
import { X, Copy, Check } from 'lucide-react'

interface DslViewerModalProps {
  isOpen: boolean
  title: string
  subtitle?: string
  body: Record<string, unknown> | null | undefined
  onClose: () => void
}

export function DslViewerModal({ isOpen, title, subtitle, body, onClose }: DslViewerModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    dialogRef.current?.focus()

    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!copied) return
    const t = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(t)
  }, [copied])

  if (!isOpen) return null

  const json = body ? JSON.stringify(body, null, 2) : '// no DSL body available'

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(json)
      setCopied(true)
    } catch {
      // Clipboard may be unavailable (insecure context, denied permission).
      // Fail silently — the user can still select and copy manually.
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        className="bg-gray-900 rounded-lg shadow-xl border border-gray-700 max-w-3xl w-full max-h-[80vh] flex flex-col"
        role="dialog"
        aria-labelledby="dsl-viewer-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 p-4 border-b border-gray-700">
          <div className="min-w-0">
            <h2 id="dsl-viewer-title" className="text-base font-semibold text-white">
              {title}
            </h2>
            {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs text-gray-300 hover:text-white hover:bg-gray-800 border border-gray-700 transition-colors"
              aria-label="Copy DSL to clipboard"
              disabled={!body}
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-green-400" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy
                </>
              )}
            </button>
            <button
              onClick={onClose}
              aria-label="Close DSL viewer"
              className="text-gray-400 hover:text-gray-200 p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          <pre className="text-xs text-gray-200 font-mono whitespace-pre bg-gray-950/60 rounded p-3 border border-gray-800">
            {json}
          </pre>
          <p className="text-[11px] text-gray-500 mt-3">
            Embedding vectors are replaced with a placeholder for readability. Paste the rest into
            OpenSearch Dashboards Dev Tools to inspect or replay.
          </p>
        </div>
      </div>
    </div>
  )
}
