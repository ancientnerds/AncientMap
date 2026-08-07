/**
 * Entry for the Story Archive routes (/news-archive/ and /news-archive/{slug}).
 *
 * The server injects window.__AN_ROUTE__ and pre-renders the same content
 * into #root, so this entry only has to pick the matching component.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import { AuthProvider } from './contexts/AuthContext'
import { OfflineProvider } from './contexts/OfflineContext'
import StoryArchivePage from './pages/StoryArchivePage'
import StoryPage from './pages/StoryPage'
import { anRoute } from './types/anRoute'
import './styles/index.css'

const route = anRoute()

function Entry() {
  if (route?.type === 'story') return <StoryPage story={route} />
  if (route?.type === 'storyArchive') {
    return (
      <StoryArchivePage
        page={route.page}
        totalPages={route.totalPages}
        total={route.total}
        stories={route.stories}
      />
    )
  }
  // Opened without server context (direct hit on /story.html) — the archive
  // is the only sensible destination.
  window.location.replace('/news-archive/')
  return null
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
      <OfflineProvider>
        <Entry />
      </OfflineProvider>
    </AuthProvider>
  </React.StrictMode>,
)
