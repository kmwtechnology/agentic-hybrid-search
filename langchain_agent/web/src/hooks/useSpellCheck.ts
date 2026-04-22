/**
 * useSpellCheck - Hook for suggesting spelling corrections using phonetic matching.
 * Leverages OpenSearch phonetic analyzer (double_metaphone) for "did you mean?" suggestions.
 */

import { useEffect, useState } from 'react'
import { apiGet } from '../utils/api'

export interface SpellingCorrection {
  original: string
  suggested: string
  confidence: number
}

/**
 * Suggests spelling corrections based on phonetic similarity.
 * Uses OpenSearch phonetic matching to find similar-sounding products/terms.
 *
 * @param query - The user's input query
 * @param onCorrection - Callback when a correction is found
 */
export function useSpellCheck(query: string, onCorrection?: (correction: SpellingCorrection) => void) {
  const [correction, setCorrection] = useState<SpellingCorrection | null>(null)
  const [isChecking, setIsChecking] = useState(false)

  useEffect(() => {
    if (!query.trim() || query.trim().length < 3) {
      setCorrection(null)
      return
    }

    const checkSpelling = async () => {
      setIsChecking(true)

      try {
        // Try to get suggestions for the query
        // If results are poor (low relevance), suggest phonetic alternatives
        const response = await apiGet(
          `/api/suggest?q=${encodeURIComponent(query)}&limit=1`
        )

        if (response.ok) {
          const data = await response.json()
          // For now, we show suggestions if they have lower confidence
          // In a more advanced implementation, we'd compare phonetic scores
          if (data.suggestions && data.suggestions.length > 0 && data.suggestions[0].score < 0.7) {
            const suggestion: SpellingCorrection = {
              original: query,
              suggested: data.suggestions[0].title,
              confidence: data.suggestions[0].score || 0.7,
            }
            setCorrection(suggestion)
            onCorrection?.(suggestion)
          } else {
            setCorrection(null)
          }
        }
      } catch (err) {
        // Silently fail on spell check - it's not critical
        setCorrection(null)
      } finally {
        setIsChecking(false)
      }
    }

    // Debounce spell check
    const timer = setTimeout(checkSpelling, 500)
    return () => clearTimeout(timer)
  }, [query, onCorrection])

  return { correction, isChecking }
}
