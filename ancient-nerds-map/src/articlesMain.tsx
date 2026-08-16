import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from './contexts/AuthContext'
import ArticlesPage from './pages/ArticlesPage'
import { RouteProvider, readInjectedRoute } from './seo/RouteContext'
import './styles/index.css'

// /articles/{slug} is served by the API inside this shell; ArticlesPage
// selects an article from the hash, so seed it before the first render.
const route = readInjectedRoute()
if (route?.type === 'article' && !window.location.hash) {
  window.history.replaceState(null, '', `${window.location.pathname}#${route.slug}`)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouteProvider value={route}>
      <AuthProvider>
        <ArticlesPage />
      </AuthProvider>
    </RouteProvider>
  </React.StrictMode>,
)
