import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Landing } from './pages/Landing'
import { EvScreen } from './pages/EvScreen'
import { Movement } from './pages/Movement'
import { TrackRecord } from './pages/TrackRecord'
import { Pricing } from './pages/Pricing'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="ev" element={<EvScreen />} />
        <Route path="movement" element={<Movement />} />
        <Route path="track-record" element={<TrackRecord />} />
        <Route path="pricing" element={<Pricing />} />
        <Route path="*" element={<Landing />} />
      </Route>
    </Routes>
  )
}
