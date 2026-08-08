import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Landing } from './pages/Landing'
import { LessonsFlow } from './pages/LessonsFlow'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="extract" element={<LessonsFlow />} />
          <Route path="lessons" element={<Navigate to="/extract" replace />} />
          <Route path="mentor" element={<Navigate to="/extract" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
