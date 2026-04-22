/**
 * SearchOptimizationDetails - Shows query optimizations applied by OpenSearch.
 * Displays: hybrid search balance (alpha), fuzzy matching, synonym expansion, phonetic matching.
 */

import { ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import clsx from 'clsx'

interface SearchOptimization {
  name: string
  status: 'enabled' | 'applied' | 'disabled'
  description: string
  icon: string
}

const OPTIMIZATIONS: SearchOptimization[] = [
  {
    name: 'Hybrid Search',
    status: 'enabled',
    description: 'Combines semantic (vector) and lexical (BM25) search for best results',
    icon: '🔄',
  },
  {
    name: 'Fuzzy Matching',
    status: 'enabled',
    description: 'Tolerates spelling variations (e.g., "Sony" matches "Sonie")',
    icon: '🎯',
  },
  {
    name: 'Synonym Expansion',
    status: 'enabled',
    description: 'Expands queries (e.g., "headphones" → "earphones/earbuds")',
    icon: '🔗',
  },
  {
    name: 'Phonetic Matching',
    status: 'enabled',
    description: 'Finds phonetically similar terms (e.g., "Sennheiser")',
    icon: '🔊',
  },
  {
    name: 'Phrase Boosting',
    status: 'enabled',
    description: 'Ranks exact phrases higher (e.g., "noise cancelling")',
    icon: '📝',
  },
  {
    name: 'Field Boosting',
    status: 'enabled',
    description: 'Prioritizes matches in important fields (title, brand)',
    icon: '⭐',
  },
  {
    name: 'Typeahead Autocomplete',
    status: 'enabled',
    description: 'Edge-ngram prefix suggestions as you type (title + brand)',
    icon: '⌨️',
  },
]

export function SearchOptimizationDetails() {
  const [isExpanded, setIsExpanded] = useState(true)

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between hover:bg-gray-700/30 p-2 -m-2 rounded transition-colors"
      >
        <h3 className="font-semibold text-gray-100 flex items-center gap-2">
          <span>🔍 Search Optimizations</span>
        </h3>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {isExpanded && (
        <div className="mt-3 space-y-2">
          {OPTIMIZATIONS.map((opt) => (
            <div
              key={opt.name}
              className={clsx(
                'p-2 rounded text-sm transition-colors',
                opt.status === 'enabled' ? 'bg-green-900/20 border border-green-800/50' : 'bg-gray-700/20 border border-gray-700/50'
              )}
            >
              <div className="flex items-start gap-2">
                <span className="text-lg">{opt.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-100">{opt.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{opt.description}</div>
                </div>
                <div
                  className={clsx(
                    'text-xs font-medium whitespace-nowrap ml-2',
                    opt.status === 'enabled' ? 'text-green-400' : 'text-gray-500'
                  )}
                >
                  {opt.status === 'enabled' && '✓ On'}
                  {opt.status === 'applied' && '✓ Applied'}
                  {opt.status === 'disabled' && '○ Off'}
                </div>
              </div>
            </div>
          ))}

          <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-500">
            <p className="mb-2">💡 <strong>Tip:</strong> These optimizations work automatically to improve search accuracy.</p>
            <p>Try searching for:</p>
            <ul className="list-disc list-inside text-gray-600 mt-1 space-y-1">
              <li>Misspelled terms (e.g., "sonie" for Sony)</li>
              <li>Product alternatives (e.g., "earbuds" for headphones)</li>
              <li>Phonetic variants (e.g., "Sennheiser")</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
