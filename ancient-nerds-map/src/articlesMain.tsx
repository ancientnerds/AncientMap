import React from 'react'
import ReactDOM from 'react-dom/client'
import ArticlesPage from './pages/ArticlesPage'
import './styles/index.css'

document.body.classList.add('theme-white')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ArticlesPage />
  </React.StrictMode>,
)
