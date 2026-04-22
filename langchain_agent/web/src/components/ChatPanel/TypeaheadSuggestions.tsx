/**
 * TypeaheadSuggestions - Autocomplete dropdown with ARIA combobox semantics.
 *
 * Sections (top to bottom):
 *   1. "Did you mean: X?" spell-correction banner (if present)
 *   2. Product suggestions with highlighted match fragments
 *   3. Recent searches (when input is empty)
 */

import clsx from 'clsx'
import { History, Lightbulb, Search, SpellCheck2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiGet } from '../../utils/api'
import { useRecentSearches } from '../../hooks/useRecentSearches'

export interface Suggestion {
  title: string
  brand?: string
  type: 'product' | 'spelling' | 'recent'
  score?: number
  highlight?: string[]
}

interface BackendSuggestion {
  title: string
  brand?: string | null
  score?: number | null
  highlight?: string[] | null
}

interface BackendResponse {
  suggestions: BackendSuggestion[]
  spell_correction: BackendSuggestion | null
}

interface TypeaheadSuggestionsProps {
  query: string
  isOpen: boolean
  selectedIndex: number
  listboxId: string
  onSelect: (suggestion: Suggestion) => void
  onRowCountChange?: (count: number) => void
}

const HL_PRE = '<mark data-th>'
const HL_POST = '</mark>'

/** Render a highlighted OpenSearch fragment as React nodes. No dangerouslySetInnerHTML. */
function HighlightedText({ fragment, fallback }: { fragment?: string; fallback: string }) {
  if (!fragment) return <>{fallback}</>

  const nodes: React.ReactNode[] = []
  let cursor = 0
  let key = 0
  while (cursor < fragment.length) {
    const start = fragment.indexOf(HL_PRE, cursor)
    if (start === -1) {
      nodes.push(fragment.slice(cursor))
      break
    }
    if (start > cursor) {
      nodes.push(fragment.slice(cursor, start))
    }
    const end = fragment.indexOf(HL_POST, start + HL_PRE.length)
    if (end === -1) {
      nodes.push(fragment.slice(start))
      break
    }
    const inner = fragment.slice(start + HL_PRE.length, end)
    nodes.push(
      <mark key={key++} className="bg-yellow-500/30 text-yellow-100 rounded px-0.5">
        {inner}
      </mark>
    )
    cursor = end + HL_POST.length
  }

  return <>{nodes.length > 0 ? nodes : fallback}</>
}

export function TypeaheadSuggestions({
  query,
  isOpen,
  selectedIndex,
  listboxId,
  onSelect,
  onRowCountChange,
}: TypeaheadSuggestionsProps) {
  const [products, setProducts] = useState<Suggestion[]>([])
  const [spelling, setSpelling] = useState<Suggestion | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { recent, clear: clearRecent } = useRecentSearches()

  const trimmed = query.trim()
  const showRecent = trimmed.length === 0 && recent.length > 0

  useEffect(() => {
    if (!trimmed || !isOpen) {
      setProducts([])
      setSpelling(null)
      return
    }

    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setIsLoading(true)
      setError(null)
      try {
        const response = await apiGet(`/api/suggest?q=${encodeURIComponent(trimmed)}`, {
          signal: controller.signal,
        })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = (await response.json()) as BackendResponse
        setProducts(
          (data.suggestions || []).map((s) => ({
            title: s.title,
            brand: s.brand ?? undefined,
            score: s.score ?? undefined,
            highlight: s.highlight ?? undefined,
            type: 'product' as const,
          }))
        )
        setSpelling(
          data.spell_correction
            ? {
                title: data.spell_correction.title,
                brand: data.spell_correction.brand ?? undefined,
                score: data.spell_correction.score ?? undefined,
                type: 'spelling' as const,
              }
            : null
        )
      } catch (err) {
        if ((err as { name?: string }).name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load suggestions')
        setProducts([])
        setSpelling(null)
      } finally {
        setIsLoading(false)
      }
    }, 300)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [trimmed, isOpen])

  // Flat list of rows in navigation order. Keep in sync with MessageInput's
  // selectedIndex clamp logic.
  const rows = useMemo<Suggestion[]>(() => {
    if (showRecent) {
      return recent.map((q) => ({ title: q, type: 'recent' as const }))
    }
    const list: Suggestion[] = []
    if (spelling) list.push(spelling)
    list.push(...products)
    return list
  }, [showRecent, recent, spelling, products])

  useEffect(() => {
    onRowCountChange?.(rows.length)
  }, [rows.length, onRowCountChange])

  if (!isOpen) return null
  if (!trimmed && !showRecent) return null

  const resultsCount = rows.length

  return (
    <div
      role="listbox"
      id={listboxId}
      aria-label="Search suggestions"
      className="absolute bottom-full mb-2 left-0 right-0 bg-gray-800 border border-gray-700 rounded-lg shadow-xl overflow-hidden max-h-96 overflow-y-auto z-50"
    >
      {/* Loading skeleton */}
      {!showRecent && isLoading && (
        <div role="status" aria-live="polite" className="py-2">
          <span className="sr-only">Loading suggestions</span>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="px-4 py-2 flex items-center gap-3">
              <div className="w-4 h-4 rounded bg-gray-700/60 animate-pulse" />
              <div className="h-3 rounded bg-gray-700/60 animate-pulse flex-1" />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!showRecent && error && !isLoading && (
        <div role="status" aria-live="polite" className="px-4 py-3 text-sm text-red-400">
          Could not load suggestions
        </div>
      )}

      {/* Empty */}
      {!showRecent && !isLoading && !error && rows.length === 0 && (
        <div role="status" aria-live="polite" className="px-4 py-3 text-sm text-gray-500">
          No products found for &ldquo;{trimmed}&rdquo;
        </div>
      )}

      {/* Recent searches header */}
      {showRecent && (
        <div className="flex items-center justify-between px-4 py-2 text-xs uppercase tracking-wide text-gray-500 border-b border-gray-700">
          <span className="flex items-center gap-1.5">
            <History className="w-3 h-3" />
            Recent
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              clearRecent()
            }}
            className="flex items-center gap-1 text-gray-500 hover:text-gray-300 transition-colors"
            aria-label="Clear recent searches"
          >
            <X className="w-3 h-3" />
            Clear
          </button>
        </div>
      )}

      {/* Rows */}
      {rows.map((row, index) => {
        const selected = index === selectedIndex
        const optionId = `typeahead-option-${index}`
        const isSpelling = row.type === 'spelling'
        const isRecent = row.type === 'recent'
        return (
          <button
            key={`${row.type}-${index}-${row.title}`}
            id={optionId}
            type="button"
            role="option"
            aria-selected={selected}
            onMouseDown={(e) => {
              // Prevent textarea blur so onSelect fires before blur-timer closes dropdown.
              e.preventDefault()
            }}
            onClick={() => onSelect(row)}
            className={clsx(
              'w-full text-left px-4 py-2 text-sm transition-colors border-b border-gray-700 last:border-b-0',
              selected
                ? 'bg-blue-600/20 text-blue-300'
                : 'hover:bg-gray-700/50 text-gray-200'
            )}
          >
            <div className="flex items-start gap-3">
              {isSpelling ? (
                <SpellCheck2 className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-400" />
              ) : isRecent ? (
                <History className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
              ) : (
                <Search className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
              )}
              <div className="flex-1 min-w-0">
                {isSpelling ? (
                  <div className="truncate">
                    <span className="text-xs text-amber-400 font-medium">Did you mean: </span>
                    <span className="font-medium">{row.title}</span>
                  </div>
                ) : (
                  <div className="truncate font-medium">
                    <HighlightedText fragment={row.highlight?.[0]} fallback={row.title} />
                  </div>
                )}
                {row.brand && !isSpelling && (
                  <div className="text-xs text-gray-400 truncate">{row.brand}</div>
                )}
                {row.score !== undefined && row.score < 1 && !isRecent && (
                  <div className="text-xs text-gray-500 mt-0.5">
                    Match: {(row.score * 100).toFixed(0)}%
                  </div>
                )}
              </div>
            </div>
          </button>
        )
      })}

      {/* Hint */}
      <div className="px-4 py-2 text-xs text-gray-500 bg-gray-900/50 border-t border-gray-700">
        <span role="status" aria-live="polite" className="sr-only">
          {resultsCount > 0 ? `${resultsCount} suggestions available` : ''}
        </span>
        <Lightbulb className="w-3 h-3 inline mr-1" />
        {showRecent ? 'Recent searches · press Enter to reuse' : 'Use arrow keys · Enter to accept · Esc to close'}
      </div>
    </div>
  )
}
