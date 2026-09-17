import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { ChatDashboard } from '@/features/chat/components/ChatDashboard'
import { WelcomePage } from '@/pages/WelcomePage'
import { RequireAuth, RequireAdmin } from '@/features/auth/components/RouteGuards'
import { ChatProvider } from '@/features/chat/ChatProvider'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { AdminLayout } from '@/app/layouts/AdminLayout'
import { CollectionDetailPage } from '@/features/collections/pages/CollectionDetailPage'
import { CollectionNewPage } from '@/features/collections/pages/CollectionNewPage'
import { CollectionsPage } from '@/features/collections/pages/CollectionsPage'

function PublicLayout() {
  return <ChatProvider><Outlet /></ChatProvider>
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route path="/" element={<WelcomePage />} />
        <Route path="/chat" element={<ChatDashboard />} />
      </Route>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<RequireAdmin />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<CollectionsPage />} />
            <Route path="collections/new" element={<CollectionNewPage />} />
            <Route path="collections/:id" element={<CollectionDetailPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

