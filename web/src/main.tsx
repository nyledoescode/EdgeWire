import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { TierProvider } from './auth/TierContext'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <TierProvider>
        <App />
      </TierProvider>
    </BrowserRouter>
  </StrictMode>,
)
