/**
 * Protected Route Component
 * Wraps routes that require authentication and/or specific permissions
 */
import React from 'react';
import { Navigate } from 'react-router-dom';
import teamAuthService from './TeamAuthService';
import { usePermissions } from './usePermissions';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPermissions?: string[];
  requireAll?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredPermissions = [],
  requireAll = false,
}) => {
  const { hasAnyPermission, hasAllPermissions, loading } = usePermissions();

  // Check authentication
  if (!teamAuthService.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  // Wait for permissions to load
  if (loading) {
    return <div>Loading...</div>;
  }

  // Check permissions if required
  if (requiredPermissions.length > 0) {
    const hasAccess = requireAll
      ? hasAllPermissions(requiredPermissions)
      : hasAnyPermission(requiredPermissions);

    if (!hasAccess) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
};

/**
 * Usage in App.tsx:
 * 
 * <Route
 *   path="/payments"
 *   element={
 *     <ProtectedRoute req