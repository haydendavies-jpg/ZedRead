/** Root application component — router + providers. */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import { PrivateRoute } from './components/PrivateRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { GroupsPage } from './pages/GroupsPage'
import { BrandsPage } from './pages/BrandsPage'
import { SitesPage } from './pages/SitesPage'
import { LicensesPage } from './pages/LicensesPage'
import { PortalUsersPage } from './pages/PortalUsersPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route
              element={
                <PrivateRoute>
                  <Layout />
                </PrivateRoute>
              }
            >
              <Route index element={<Navigate to="/groups" replace />} />
              <Route path="groups" element={<GroupsPage />} />
              <Route path="brands" element={<BrandsPage />} />
              <Route path="sites" element={<SitesPage />} />
              <Route path="licenses" element={<LicensesPage />} />
              <Route
                path="portal-users"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <PortalUsersPage />
                  </PrivateRoute>
                }
              />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
