/**
 * API Documentation page displaying Swagger UI.
 * Embeds the backend's /docs endpoint via iframe.
 */

import { useEffect, useState } from 'react'

export function DocsPage() {
  const [docsUrl, setDocsUrl] = useState<string>('http://localhost:8000/docs')

  useEffect(() => {
    // Determine the correct docs URL based on environment
    const fetchApiUrl = async () => {
      try {
        const response = await fetch('/api/config')
        const config = await response.json()

        if (config.apiUrl) {
          setDocsUrl(`${config.apiUrl}/docs`)
        } else {
          // Dev environment: use localhost:8000
          const hostname = window.location.hostname
          const port = hostname === 'localhost' || hostname === '127.0.0.1' ? 8000 : undefined
          const url = port ? `http://localhost:${port}/docs` : `${window.location.origin}/docs`
          setDocsUrl(url)
        }
      } catch (err) {
        console.error('Failed to fetch API config, using default:', err)
        // Keep default localhost:8000
      }
    }

    fetchApiUrl()
  }, [])

  return (
    <div className="h-screen w-screen bg-white overflow-hidden">
      <iframe
        src={docsUrl}
        title="API Documentation"
        className="w-full h-full border-0"
        sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
      />
    </div>
  )
}
