/**
 * Root application component — router + providers.
 *
 * Routes are split by user type:
 *   Admin-portal routes (/groups, /brands, /sites, /licenses, /users)
 *   Management routes  (/management/menu-studio, /tax, /reports, /users, /access-profiles)
 *
 * The Layout sidebar adapts based on JWT type (portal_access vs mgmt_access).
 * PrivateRoute enforces authentication; requireSuperAdmin guards admin-only routes.
 */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth, isMgmtUser } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { PrivateRoute } from './components/PrivateRoute'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { GroupsPage } from './pages/GroupsPage'
import { BrandsPage } from './pages/BrandsPage'
import { SitesPage } from './pages/SitesPage'
import { LicensesPage } from './pages/LicensesPage'
import { BrandDetailPage } from './pages/brands/BrandDetailPage'
import { GroupDetailPage } from './pages/groups/GroupDetailPage'
import { SiteDetailPage } from './pages/sites/SiteDetailPage'
import { ProductsPage } from './pages/management/ProductsPage'
import { ModifiersPage } from './pages/management/ModifiersPage'
import { CategoriesPage } from './pages/management/CategoriesPage'
import { MenuBuilderPage } from './pages/management/MenuBuilderPage'
import { MenuStudioPage } from './pages/management/MenuStudioPage'
import { ReportsPage } from './pages/management/ReportsPage'
import { InvoicesPage } from './pages/management/InvoicesPage'
import { InvoiceDetailPage } from './pages/management/InvoiceDetailPage'
import { UsersPage as MgmtUsersPage } from './pages/management/UsersPage'
import { AccessProfilesPage } from './pages/management/AccessProfilesPage'
import { CompanyProfilePage } from './pages/management/CompanyProfilePage'
import { UsersPage } from './pages/UsersPage'
import { EmailTemplatesPage } from './pages/EmailTemplatesPage'
import { TaxTemplatesPage } from './pages/TaxTemplatesPage'

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
      <ThemeProvider>
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
              {/* Default redirect — SuperAdmins → /groups, mgmt users → /management/menu-studio */}
              <Route index element={<SmartRedirect />} />

              {/* SuperAdmin routes */}
              <Route
                path="groups"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <GroupsPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="groups/:groupId"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <GroupDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="brands"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <BrandsPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="brands/:brandId"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <BrandDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="sites"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <SitesPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="sites/:siteId"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <SiteDetailPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="licenses"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <LicensesPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="users"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <UsersPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="email-templates"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <EmailTemplatesPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="tax-templates"
                element={
                  <PrivateRoute requireSuperAdmin>
                    <TaxTemplatesPage />
                  </PrivateRoute>
                }
              />

              {/* Management routes — available to both SuperAdmin and management users */}
              <Route path="management" element={<Navigate to="/management/menu-studio" replace />} />
              <Route path="management/menu-studio" element={<MenuStudioPage />} />
              <Route path="management/products" element={<ProductsPage />} />
              <Route path="management/modifiers" element={<ModifiersPage />} />
              <Route path="management/categories" element={<CategoriesPage />} />
              <Route path="management/menu-builder" element={<MenuBuilderPage />} />
              <Route path="management/reports" element={<ReportsPage />} />
              <Route path="management/invoices" element={<InvoicesPage />} />
              <Route path="management/invoices/:invoiceId" element={<InvoiceDetailPage />} />
              <Route path="management/users" element={<MgmtUsersPage />} />
              <Route path="management/access-profiles" element={<AccessProfilesPage />} />
              <Route path="management/company-profile" element={<CompanyProfilePage />} />
            </Route>

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

/** Redirect to the appropriate landing page based on user type. */
function SmartRedirect() {
  const { user } = useAuth()
  if (isMgmtUser(user)) return <Navigate to="/management/menu-studio" replace />
  return <Navigate to="/groups" replace />
}
