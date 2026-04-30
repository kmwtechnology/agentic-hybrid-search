/**
 * Swagger UI page.
 * Embeds the backend's /swagger endpoint (FastAPI's auto-generated docs)
 * via iframe.
 */

import { useEffect, useState } from 'react'

export function SwaggerPage() {
  const [swaggerUrl, setSwaggerUrl] = useState<string>('http://localhost:8000/swagger')

  useEffect(() => {
    // Determine the correct swagger URL based on environment
    const fetchApiUrl = async () => {
      try {
        const response = await fetch('/api/config')
        const config = await response.json()

        if (config.apiUrl) {
          setSwaggerUrl(`${config.apiUrl}/swagger`)
        } else {
          // Dev environment: use localhost:8000
          const hostname = window.location.hostname
          const port = hostname === 'localhost' || hostname === '127.0.0.1' ? 8000 : undefined
          const url = port
            ? `http://localhost:${port}/swagger`
            : `${window.location.origin}/swagger`
          setSwaggerUrl(url)
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
        src={swaggerUrl}
        title="Swagger UI"
        className="w-full h-full border-0"
        sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
      />
    </div>
  )
}
