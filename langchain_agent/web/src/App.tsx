import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DocsPage } from './pages/DocsPage'
import { GuidePage } from './pages/GuidePage'
import { useChatStore } from './stores/chatStore'
import { useWebSocket } from './hooks/useWebSocket'

function ChatApp() {
  const threadId = useChatStore((s) => s.threadId)
  const setThreadId = useChatStore((s) => s.setThreadId)
  const { connect } = useWebSocket()

  // Generate initial thread ID if needed
  useEffect(() => {
    if (!threadId) {
      const newThreadId = `conversation_${Math.random().toString(36).slice(2, 10)}`
      setThreadId(newThreadId)
    }
  }, [threadId, setThreadId])

  // Connect WebSocket when thread ID changes
  useEffect(() => {
    if (threadId) {
      // Small delay to let previous connection close
      const timer = setTimeout(() => {
        connect(threadId)
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [threadId, connect])

  return <Layout />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatApp />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="/guide" element={<GuidePage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
