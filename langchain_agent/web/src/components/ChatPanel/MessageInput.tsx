/**
 * MessageInput - Chat input form with send button, typeahead, and spell check.
 */

import { useState, useRef, useCallback, useLayoutEffect, useEffect, KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useChatStore } from '../../stores/chatStore'
import { TypeaheadSuggestions, type Suggestion } from './TypeaheadSuggestions'
import clsx from 'clsx'

export function MessageInput() {
  const [message, setMessage] = useState('')
  const [showTypeahead, setShowTypeahead] = useState(false)
  const [typeaheadIndex, setTypeaheadIndex] = useState(0)
  const { sendMessage } = useWebSocket()
  const { isConnected, connectionError, inputFocusTrigger } = useChatStore()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [textareaHeight, setTextareaHeight] = useState<number>(0)

  // Focus input when triggered (after streaming completes)
  useEffect(() => {
    if (inputFocusTrigger > 0 && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [inputFocusTrigger])

  const handleSuggestionSelect = useCallback((suggestion: Suggestion) => {
    // When user selects a product from typeahead, insert it into the message
    const trimmed = message.trim()
    const newMessage = trimmed ? `${trimmed} ${suggestion.title}` : suggestion.title
    setMessage(newMessage)
    setShowTypeahead(false)
    setTypeaheadIndex(0)
  }, [message])

  const handleSubmit = useCallback(() => {
    const trimmed = message.trim()
    if (!trimmed || !isConnected) return

    // Close typeahead when submitting
    setShowTypeahead(false)
    sendMessage(trimmed)
    setMessage('')
  }, [message, sendMessage, isConnected])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Handle typeahead navigation
      if (showTypeahead) {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setTypeaheadIndex((i) => i + 1)
          return
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setTypeaheadIndex((i) => Math.max(0, i - 1))
          return
        } else if (e.key === 'Escape') {
          e.preventDefault()
          setShowTypeahead(false)
          return
        }
      }

      // Handle submit
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit, showTypeahead]
  )

  const canSend = message.trim() && isConnected

  useLayoutEffect(() => {
    if (!textareaRef.current) return

    setTextareaHeight(textareaRef.current.offsetHeight)

    let observer: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const height =
            entry.borderBoxSize?.[0]?.blockSize ||
            entry.contentRect?.height ||
            textareaRef.current?.offsetHeight ||
            entry.target.scrollHeight
          if (height) {
            setTextareaHeight(height)
          }
        }
      })

      observer.observe(textareaRef.current)
    }

    return () => {
      observer?.disconnect()
    }
  }, [message])

  return (
    <div className="p-4">
      <div className="flex items-stretch gap-2">
        <div className="flex-1 relative" ref={containerRef}>
          <label htmlFor="message-input" className="sr-only">
            Chat message
          </label>
          <textarea
            id="message-input"
            ref={textareaRef}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value)
              // Show typeahead when user has typed at least 2 characters
              setShowTypeahead(e.target.value.trim().length >= 2)
              setTypeaheadIndex(0)
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => message.trim().length >= 2 && setShowTypeahead(true)}
            onBlur={() => {
              // Delay closing to allow click selection
              setTimeout(() => setShowTypeahead(false), 200)
            }}
            placeholder={
              isConnected
                ? "Search for products, compare brands, or ask questions... (type to see suggestions)"
                : "Connecting..."
            }
            disabled={!isConnected}
            rows={1}
            aria-label="Chat message"
            aria-invalid={!isConnected ? 'true' : 'false'}
            aria-describedby={!isConnected ? 'connection-status' : undefined}
            className={clsx(
              'w-full resize-none rounded-lg border bg-gray-800 px-4 py-3 text-sm',
              'text-gray-100 placeholder-gray-400',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              isConnected ? 'border-gray-700' : 'border-yellow-600'
            )}
            style={{
              minHeight: '44px',
              maxHeight: '200px',
            }}
          />
          {/* Typeahead suggestions dropdown */}
          <TypeaheadSuggestions
            query={message}
            isOpen={showTypeahead && isConnected}
            selectedIndex={typeaheadIndex}
            onSelect={handleSuggestionSelect}
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={!canSend}
          aria-label="Send message"
          aria-disabled={!canSend}
          className={clsx(
            'flex-shrink-0 self-stretch w-12 flex items-center justify-center rounded-lg transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900',
            canSend
              ? 'bg-blue-600 hover:bg-blue-700 text-white'
              : 'bg-gray-700 text-gray-500 cursor-not-allowed'
          )}
          style={textareaHeight ? { height: `${textareaHeight}px` } : undefined}
        >
          <Send className="w-5 h-5" />
        </button>
      </div>

      {/* Connection status */}
      {!isConnected && (
        <div
          id="connection-status"
          className={clsx(
            'mt-2 text-xs font-medium',
            connectionError
              ? 'text-red-400'
              : 'text-yellow-500'
          )}
        >
          {connectionError ? (
            <div className="flex items-center gap-2">
              <span>⚠️ {connectionError}</span>
              <span className="text-xs text-gray-500">(Check that the server is running)</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="inline-block w-1.5 h-1.5 bg-yellow-500 rounded-full animate-pulse" />
              Connecting to server...
            </div>
          )}
        </div>
      )}
    </div>
  )
}
