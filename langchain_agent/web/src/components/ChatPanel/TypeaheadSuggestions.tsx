/**
 * TypeaheadSuggestions - Dropdown menu showing product suggestions and spell check.
 * Integrates with /api/suggest endpoint for autocomplete functionality.
 */

import { useEffect, useState, useCallback } from 'react'
import { Search, Lightbulb } from 'lucide-react'
import { apiGet } from '../../utils/api'
import clsx from 'clsx'

export interface Suggestion {
  title: string
  brand?: string
  type: 'product' | 'spelling'
  score?: number
}

interface TypeaheadSuggestionsProps {
  query: string
  isOpen: boolean
  selectedIndex: number
  onSelect: (suggestion: Suggestion) => void
  onClose: () => void
}

export function TypeaheadSuggestions({
  query,
  isOpen,
  selectedIndex,
  onSelect,
  onClose,
}: TypeaheadSuggestionsProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch suggestions when query changes
  useEffect(() => {
    if (!query.trim() || !isOpen) {
      setSuggestions([])
      return
    }

    const fetchSuggestions = async () => {
      setIsLoading(true)
      setError(null)

      try {
        const response = await apiGet(`/api/suggest?q=${encodeURIComponent(query)}`)

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()

        // Format suggestions from API response
        const formatted: Suggestion[] = data.suggestions?.map(
          (item: any) => ({
            title: item.title || item.product_title || item.name,
            brand: item.brand || item.product_brand,
            type: 'product' as const,
            score: item.score,
          })
        ) || []

        setSuggestions(formatted)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load suggestions')
        setSuggestions([])
      } finally {
        setIsLoading(false)
      }
    }

    // Debounce the fetch to avoid too many requests
    const timer = setTimeout(fetchSuggestions, 300)

    return () => clearTimeout(timer)
  }, [query, isOpen])

  if (!isOpen || !query.trim()) {
    return null
  }

  return (
    <div className="absolute bottom-full mb-2 left-0 right-0 bg-gray-800 border border-gray-700 rounded-lg shadow-xl overflow-hidden max-h-96 overflow-y-auto z-50">
      {/* Loading state */}
      {isLoading && (
        <div className="px-4 py-3 text-sm text-gray-400 flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-500 border-t-blue-500 rounded-full animate-spin" />
          Loading suggestions...
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="px-4 py-3 text-sm text-red-400">
          Could not load suggestions
        </div>
      )}

      {/* No suggestions */}
      {!isLoading && !error && suggestions.length === 0 && (
        <div className="px-4 py-3 text-sm text-gray-500">
          No products found for "{query}"
        </div>
      )}

      {/* Product suggestions */}
      {suggestions.map((suggestion, index) => (
        <button
          key={`${suggestion.type}-${index}`}
          onClick={() => onSelect(suggestion)}
          className={clsx(
            'w-full text-left px-4 py-2 text-sm transition-colors border-b border-gray-700 last:border-b-0',
            index === selectedIndex
              ? 'bg-blue-600/20 text-blue-300'
              : 'hover:bg-gray-700/50 text-gray-200'
          )}
        >
          <div className="flex items-start gap-3">
            <Search className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500" />
            <div className="flex-1 min-w-0">
              <div className="truncate font-medium">{suggestion.title}</div>
              {suggestion.brand && (
                <div className="text-xs text-gray-400 truncate">
                  {suggestion.brand}
                </div>
              )}
              {suggestion.score !== undefined && suggestion.score < 1 && (
                <div className="text-xs text-gray-500 mt-0.5">
                  Match: {(suggestion.score * 100).toFixed(0)}%
                </div>
              )}
            </div>
          </div>
        </button>
      ))}

      {/* Hint text */}
      <div className="px-4 py-2 text-xs text-gray-500 bg-gray-900/50 border-t border-gray-700">
        <Lightbulb className="w-3 h-3 inline mr-1" />
        Type to search products • Use arrow keys to navigate
      </div>
    </div>
  )
}
