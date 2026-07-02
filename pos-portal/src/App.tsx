/**
 * Root application component — router + providers.
 *
 * Routes are split by user type:
 *   Portal admin routes (/groups, /brands, /sites, /licenses, /portal-users)
 *   Management routes   (/management/products, /categories, /tax, /reports, /users)
 *
 * The Layout sidebar adapts based on JWT type (portal_access vs mgmt_access).
 * PrivateRoute enforces authentication; requirePortalUser guards admin-only routes.
 */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth, isMgmtUser } from './context/AuthContext'
import { PrivateRoute } from './components/PrivateRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { GroupsPage } from './pages/GroupsPage'
import { BrandsPage } from './pages/BrandsPage'
import { SitesPage } from './pages/SitesPage'
import { LicensesPage } from './pages/LicensesPage'
import { PortalUsersPage } from './pages/PortalUsersPage'
import { BrandDetailPage } from './pages/brands/BrandDetailPage'
import { GroupDetailPage } from './pages/groups/GroupDetailPage'
import { SiteDetailPage } from './pages/sites/SiteDetailPage'
import { ProductsPage } from './pages/management/ProductsPage'
import { CategoriesPage } from './pages/management/CategoriesPage'
import { TaxPage } from './pages/management/TaxPage'
import { ReportsPage } from './pages/management/ReportsPage'
import { UsersPage } from './pages/management/UsersPage'
import { SiteOverridesPage } from './pages/management/SiteOverridesPage'
import { CompanyProfilePage } from './pages/management/CompanyProfilePage'
import { PosUsersPage } from './pages/PosUsersPage'
import { EmailTemplatesPage } from './pages/EmailTemplatesPage'

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
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            <Route
              element={
                <PrivateRoute>
                  <Layout />
                </PrivateRoute>
              }
            >
              {/* Default redirect — portal users → /groups, mgmt users → /management/products */}
              <Route index element={<SmartRedirect />} />

              {/* Portal admin routes */}
              <Route
                path="groups"
                element={
                  <PrivateRoute requirePortalUser>
                    <GroupsPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="groups/:groupId"
                element={
                  <PrivateRoute requirePortalUser>
                    <GroupDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="brands"
                element={
                  <PrivateRoute requirePortalUser>
                    <BrandsPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="brands/:brandId"
                element={
                  <PrivateRoute requirePortalUser>
                    <BrandDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="sites"
                element={
                  <PrivateRoute requirePortalUser>
                    <SitesPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="sites/:siteId"
                element={
                  <PrivateRoute requirePortalUser>
                    <SiteDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="licenses"
                element={
                  <PrivateRoute requirePortalUser>
                    <LicensesPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="portal-users"
                element={
                  <PrivateRoute requirePortalUser>
                    <PortalUsersPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="pos-users"
                element={
                  <PrivateRoute requirePortalUser>
                    <PosUsersPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="email-templates"
                element={
                  <PrivateRoute requirePortalUser>
                    <EmailTemplatesPage />
                  </PrivateRoute>
                }
              />

              {/* Management routes — available to both portal and management users */}
              <Route path="management" element={<Navigate to="/management/products" replace />} />
              <Route path="management/products" element={<ProductsPage />} />
              <Route path="management/categories" element={<CategoriesPage />} />
              <Route path="management/tax" element={<TaxPage />} />
              <Route path="management/reports" element={<ReportsPage />} />
              <Route path="management/users" element={<UsersPage />} />
              <Route path="management/overrides" element={<SiteOverridesPage />} />
              <Route path="management/company-profile" element={<CompanyProfilePage />} />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

/** Redirect to the appropriate landing page based on user type. */
function SmartRedirect() {
  const { user } = useAuth()
  if (isMgmtUser(user)) return <Navigate to="/management/products" replace />
  return <Navigate to="/groups" replace />
}
