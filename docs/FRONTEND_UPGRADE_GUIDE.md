# Frontend Upgrade Guide - Enterprise Features Integration

**Version 2.0.0** | Last Updated: March 4, 2026

Complete guide for upgrading your frontend application to support all new enterprise API endpoints in Dari for Business backend.

---

## Table of Contents

1. [Overview](#overview)
2. [API Client Setup](#api-client-setup)
3. [TypeScript Types](#typescript-types)
4. [Payment Links Integration](#payment-links-integration)
5. [Invoice System Integration](#invoice-system-integration)
6. [Subscriptions Integration](#subscriptions-integration)
7. [Refunds Integration](#refunds-integration)
8. [Analytics Dashboard](#analytics-dashboard)
9. [Team Management Integration](#team-management-integration)
10. [Webhook Handler Setup](#webhook-handler-setup)
11. [State Management](#state-management)
12. [UI Components Library](#ui-components-library)
13. [Testing Strategy](#testing-strategy)
14. [Deployment Checklist](#deployment-checklist)

---

## Overview

### What's New

The backend now supports **46 new enterprise endpoints** across 6 feature categories:

| Feature | Endpoints | UI Screens Needed |
|---------|-----------|-------------------|
| Payment Links | 6 | List, Create, Edit, Analytics |
| Invoices | 9 | List, Create, Edit, Send, View |
| Subscriptions | 12 | Plans, Subscriptions, Billing |
| Refunds | 5 | List, Process, Track |
| Analytics | 6 | Dashboard, Reports |
| Team Management | 8 | Members, Roles, Invites |

### Architecture Changes

```
Old:
Frontend → API → Payments Only

New:
Frontend → API → Payments
              → Payment Links
              → Invoices
              → Subscriptions
              → Refunds
              → Analytics
              → Team Management
```

### Technology Stack Recommendations

- **React 18+** with TypeScript
- **React Query (TanStack Query)** for API state management
- **Zustand or Redux Toolkit** for global state
- **React Router v6** for navigation
- **Tailwind CSS** for styling
- **shadcn/ui** or **Material UI** for components
- **Chart.js** or **Recharts** for analytics visualization
- **date-fns** for date formatting
- **zod** for validation

---

## API Client Setup

### Base API Client

Create a centralized API client with authentication and error handling.

**`src/lib/api-client.ts`**

```typescript
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.dariforbusiness.com';

class ApiClient {
  private client: AxiosInstance;
  private apiKey: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        const apiKey = this.getApiKey();
        if (apiKey) {
          config.headers['X-API-Key'] = apiKey;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          // Handle unauthorized
          this.handleUnauthorized();
        }
        return Promise.reject(error);
      }
    );
  }

  setApiKey(key: string) {
    this.apiKey = key;
    localStorage.setItem('dari_api_key', key);
  }

  getApiKey(): string | null {
    if (!this.apiKey) {
      this.apiKey = localStorage.getItem('dari_api_key');
    }
    return this.apiKey;
  }

  clearApiKey() {
    this.apiKey = null;
    localStorage.removeItem('dari_api_key');
  }

  private handleUnauthorized() {
    this.clearApiKey();
    window.location.href = '/login';
  }

  // Generic request method with idempotency support
  async request<T>(config: AxiosRequestConfig & { idempotencyKey?: string }): Promise<T> {
    const { idempotencyKey, ...axiosConfig } = config;
    
    if (idempotencyKey) {
      axiosConfig.headers = {
        ...axiosConfig.headers,
        'Idempotency-Key': idempotencyKey,
      };
    }

    const response = await this.client.request<T>(axiosConfig);
    return response.data;
  }

  // Convenience methods
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'GET', url });
  }

  post<T>(url: string, data?: any, config?: AxiosRequestConfig & { idempotencyKey?: string }): Promise<T> {
    return this.request({ ...config, method: 'POST', url, data });
  }

  patch<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'PATCH', url, data });
  }

  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return this.request({ ...config, method: 'DELETE', url });
  }
}

export const apiClient = new ApiClient();
```

### Environment Configuration

**`.env`**

```bash
REACT_APP_API_URL=https://api.dariforbusiness.com
REACT_APP_WEBHOOK_URL=https://yourapp.com/webhooks/dari
REACT_APP_ENABLE_ANALYTICS=true
```

---

## TypeScript Types

Define comprehensive TypeScript types for all enterprise features.

**`src/types/api.types.ts`**

```typescript
// ============================================================================
// COMMON TYPES
// ============================================================================

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type ApiError = {
  detail: string;
  code?: string;
};

// ============================================================================
// PAYMENT LINKS
// ============================================================================

export type PaymentLink = {
  id: string;
  merchant_id: string;
  name: string;
  description?: string;
  amount_fiat?: number;
  fiat_currency: string;
  is_amount_fixed: boolean;
  accepted_tokens: string[];
  accepted_chains: string[];
  success_url?: string;
  cancel_url?: string;
  is_active: boolean;
  is_single_use: boolean;
  expires_at?: string;
  view_count: number;
  payment_count: number;
  total_collected_usd: number;
  checkout_url: string;
  created_at: string;
  updated_at?: string;
};

export type CreatePaymentLinkInput = {
  name: string;
  description?: string;
  amount_fiat?: number;
  fiat_currency?: string;
  is_amount_fixed?: boolean;
  accepted_tokens: string[];
  accepted_chains: string[];
  success_url?: string;
  cancel_url?: string;
  is_single_use?: boolean;
  expires_at?: string;
};

export type UpdatePaymentLinkInput = Partial<Omit<CreatePaymentLinkInput, 'accepted_tokens' | 'accepted_chains'>> & {
  is_active?: boolean;
};

export type PaymentLinkAnalytics = {
  link_id: string;
  views: number;
  payments: number;
  conversion_rate: number;
  total_collected_usd: number;
  recent_payments: PaymentSession[];
};

// ============================================================================
// INVOICES
// ============================================================================

export enum InvoiceStatus {
  DRAFT = 'draft',
  SENT = 'sent',
  VIEWED = 'viewed',
  PAID = 'paid',
  OVERDUE = 'overdue',
  CANCELLED = 'cancelled',
}

export type InvoiceLineItem = {
  description: string;
  quantity: number;
  unit_price: number;
  total?: number;
};

export type Invoice = {
  id: string;
  invoice_number: string;
  merchant_id: string;
  customer_email: string;
  customer_name?: string;
  customer_address?: string;
  description?: string;
  line_items: InvoiceLineItem[];
  subtotal: number;
  tax: number;
  discount: number;
  total: number;
  fiat_currency: string;
  status: InvoiceStatus;
  issue_date: string;
  due_date: string;
  sent_at?: string;
  viewed_at?: string;
  paid_at?: string;
  payment_session_id?: string;
  payment_url?: string;
  accepted_tokens: string[];
  accepted_chains: string[];
  notes?: string;
  terms?: string;
  created_at: string;
  updated_at?: string;
};

export type CreateInvoiceInput = {
  customer_email: string;
  customer_name?: string;
  customer_address?: string;
  description?: string;
  line_items: InvoiceLineItem[];
  tax?: number;
  discount?: number;
  due_date: string;
  accepted_tokens: string[];
  accepted_chains: string[];
  notes?: string;
  terms?: string;
  send_immediately?: boolean;
};

export type UpdateInvoiceInput = Partial<CreateInvoiceInput>;

// ============================================================================
// SUBSCRIPTIONS
// ============================================================================

export enum SubscriptionStatus {
  ACTIVE = 'active',
  PAUSED = 'paused',
  CANCELLED = 'cancelled',
  PAST_DUE = 'past_due',
  TRIALING = 'trialing',
}

export enum SubscriptionInterval {
  DAILY = 'daily',
  WEEKLY = 'weekly',
  MONTHLY = 'monthly',
  QUARTERLY = 'quarterly',
  YEARLY = 'yearly',
}

export type SubscriptionPlan = {
  id: string;
  merchant_id: string;
  name: string;
  description?: string;
  amount: number;
  fiat_currency: string;
  interval: SubscriptionInterval;
  interval_count: number;
  trial_days: number;
  accepted_tokens: string[];
  accepted_chains: string[];
  features?: string[];
  is_active: boolean;
  subscriber_count: number;
  created_at: string;
  updated_at?: string;
};

export type Subscription = {
  id: string;
  plan_id: string;
  plan_name: string;
  merchant_id: string;
  customer_email: string;
  customer_name?: string;
  customer_id?: string;
  status: SubscriptionStatus;
  current_period_start: string;
  current_period_end: string;
  trial_start?: string;
  trial_end?: string;
  next_payment_at?: string;
  next_payment_url?: string;
  cancel_at?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
  paused_at?: string;
  created_at: string;
  updated_at?: string;
};

export type SubscriptionPayment = {
  id: string;
  subscription_id: string;
  payment_session_id: string;
  amount: number;
  fiat_currency: string;
  status: string;
  period_start: string;
  period_end: string;
  paid_at?: string;
  created_at: string;
};

export type CreateSubscriptionPlanInput = {
  name: string;
  description?: string;
  amount: number;
  fiat_currency?: string;
  interval: SubscriptionInterval;
  interval_count?: number;
  trial_days?: number;
  accepted_tokens: string[];
  accepted_chains: string[];
  features?: string[];
};

export type CreateSubscriptionInput = {
  plan_id: string;
  customer_email: string;
  customer_name?: string;
  customer_id?: string;
  skip_trial?: boolean;
};

// ============================================================================
// REFUNDS
// ============================================================================

export enum RefundStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

export type Refund = {
  id: string;
  payment_session_id: string;
  merchant_id: string;
  amount: number;
  token: string;
  chain: string;
  refund_address: string;
  status: RefundStatus;
  reason?: string;
  tx_hash?: string;
  error_message?: string;
  created_at: string;
  completed_at?: string;
  updated_at?: string;
};

export type CreateRefundInput = {
  payment_session_id: string;
  amount?: number; // Optional for full refund
  refund_address: string;
  reason?: string;
};

// ============================================================================
// ANALYTICS
// ============================================================================

export type AnalyticsOverview = {
  period_start: string;
  period_end: string;
  period: 'day' | 'week' | 'month' | 'year';
  payments: {
    total_payments: number;
    successful_payments: number;
    failed_payments: number;
    total_volume_usd: number;
    avg_payment_usd: number;
    conversion_rate: number;
  };
  volume_by_token: {
    token: string;
    volume_usd: number;
    payment_count: number;
  }[];
  volume_by_chain: {
    chain: string;
    volume_usd: number;
    payment_count: number;
  }[];
  invoices_sent: number;
  invoices_paid: number;
  invoice_volume_usd: number;
  active_subscriptions: number;
  new_subscriptions: number;
  churned_subscriptions: number;
  subscription_mrr: number;
  payments_change_pct: number;
  volume_change_pct: number;
};

export type RevenueDataPoint = {
  date: string;
  volume_usd: number;
  payment_count: number;
};

export type RevenueTimeSeries = {
  period: string;
  interval: string;
  data: RevenueDataPoint[];
};

export type ConversionMetrics = {
  period_days: number;
  total_sessions: number;
  completed_sessions: number;
  expired_sessions: number;
  conversion_rate: number;
  avg_time_to_payment_seconds: number;
};

// ============================================================================
// TEAM MANAGEMENT
// ============================================================================

export enum MerchantRole {
  OWNER = 'owner',
  ADMIN = 'admin',
  DEVELOPER = 'developer',
  FINANCE = 'finance',
  VIEWER = 'viewer',
}

export type TeamMember = {
  id: string;
  merchant_id: string;
  email: string;
  name?: string;
  role: MerchantRole;
  is_active: boolean;
  invite_pending: boolean;
  last_login?: string;
  created_at: string;
  updated_at?: string;
};

export type InviteTeamMemberInput = {
  email: string;
  name?: string;
  role: MerchantRole;
};

export type UpdateTeamMemberInput = {
  role?: MerchantRole;
  is_active?: boolean;
};

export type RolePermissions = {
  role: MerchantRole;
  permissions: string[];
  description: string;
};

// ============================================================================
// PAYMENT SESSIONS (Existing, for reference)
// ============================================================================

export type PaymentSession = {
  id: string;
  merchant_id: string;
  amount_fiat: number;
  fiat_currency: string;
  status: string;
  customer_email?: string;
  metadata?: Record<string, any>;
  checkout_url: string;
  created_at: string;
  expires_at: string;
  paid_at?: string;
};
```

---

## Payment Links Integration

### API Service

**`src/services/payment-links.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  PaymentLink,
  CreatePaymentLinkInput,
  UpdatePaymentLinkInput,
  PaymentLinkAnalytics,
  PaginatedResponse,
} from '@/types/api.types';
import { v4 as uuidv4 } from 'uuid';

export class PaymentLinksService {
  private basePath = '/payment-links';

  async createPaymentLink(input: CreatePaymentLinkInput): Promise<PaymentLink> {
    return apiClient.post<PaymentLink>(this.basePath, input, {
      idempotencyKey: uuidv4(),
    });
  }

  async listPaymentLinks(params?: {
    page?: number;
    page_size?: number;
    is_active?: boolean;
  }): Promise<PaginatedResponse<PaymentLink>> {
    return apiClient.get<PaginatedResponse<PaymentLink>>(this.basePath, { params });
  }

  async getPaymentLink(linkId: string): Promise<PaymentLink> {
    return apiClient.get<PaymentLink>(`${this.basePath}/${linkId}`);
  }

  async updatePaymentLink(linkId: string, input: UpdatePaymentLinkInput): Promise<PaymentLink> {
    return apiClient.patch<PaymentLink>(`${this.basePath}/${linkId}`, input);
  }

  async deactivatePaymentLink(linkId: string): Promise<void> {
    return apiClient.delete<void>(`${this.basePath}/${linkId}`);
  }

  async getPaymentLinkAnalytics(linkId: string): Promise<PaymentLinkAnalytics> {
    return apiClient.get<PaymentLinkAnalytics>(`${this.basePath}/${linkId}/analytics`);
  }

  async copyToClipboard(checkoutUrl: string): Promise<void> {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(checkoutUrl);
    } else {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = checkoutUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
    }
  }
}

export const paymentLinksService = new PaymentLinksService();
```

### React Query Hooks

**`src/hooks/use-payment-links.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { paymentLinksService } from '@/services/payment-links.service';
import { CreatePaymentLinkInput, UpdatePaymentLinkInput } from '@/types/api.types';
import { toast } from 'sonner';

export const PAYMENT_LINKS_QUERY_KEY = 'payment-links';

export function usePaymentLinks(page = 1, pageSize = 20, isActive?: boolean) {
  return useQuery({
    queryKey: [PAYMENT_LINKS_QUERY_KEY, { page, pageSize, isActive }],
    queryFn: () => paymentLinksService.listPaymentLinks({ page, page_size: pageSize, is_active: isActive }),
  });
}

export function usePaymentLink(linkId: string) {
  return useQuery({
    queryKey: [PAYMENT_LINKS_QUERY_KEY, linkId],
    queryFn: () => paymentLinksService.getPaymentLink(linkId),
    enabled: !!linkId,
  });
}

export function usePaymentLinkAnalytics(linkId: string) {
  return useQuery({
    queryKey: [PAYMENT_LINKS_QUERY_KEY, linkId, 'analytics'],
    queryFn: () => paymentLinksService.getPaymentLinkAnalytics(linkId),
    enabled: !!linkId,
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}

export function useCreatePaymentLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreatePaymentLinkInput) => paymentLinksService.createPaymentLink(input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [PAYMENT_LINKS_QUERY_KEY] });
      toast.success('Payment link created successfully');
      
      // Copy to clipboard
      paymentLinksService.copyToClipboard(data.checkout_url);
      toast.info('Link copied to clipboard');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create payment link');
    },
  });
}

export function useUpdatePaymentLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ linkId, input }: { linkId: string; input: UpdatePaymentLinkInput }) =>
      paymentLinksService.updatePaymentLink(linkId, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [PAYMENT_LINKS_QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: [PAYMENT_LINKS_QUERY_KEY, data.id] });
      toast.success('Payment link updated');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update payment link');
    },
  });
}

export function useDeactivatePaymentLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (linkId: string) => paymentLinksService.deactivatePaymentLink(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [PAYMENT_LINKS_QUERY_KEY] });
      toast.success('Payment link deactivated');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to deactivate payment link');
    },
  });
}
```

### React Components

**`src/components/payment-links/PaymentLinksList.tsx`**

```typescript
import React, { useState } from 'react';
import { usePaymentLinks } from '@/hooks/use-payment-links';
import { PaymentLink } from '@/types/api.types';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Copy, ExternalLink, Edit, Trash2, BarChart3 } from 'lucide-react';

export function PaymentLinksList() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = usePaymentLinks(page, 20);

  if (isLoading) return <div>Loading payment links...</div>;
  if (error) return <div>Error loading payment links</div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Payment Links</h2>
        <Button onClick={() => window.location.href = '/payment-links/new'}>
          Create Payment Link
        </Button>
      </div>

      <div className="grid gap-4">
        {data?.items.map((link) => (
          <PaymentLinkCard key={link.id} link={link} />
        ))}
      </div>

      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button
            variant="outline"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="py-2 px-4">
            Page {page} of {data.pages}
          </span>
          <Button
            variant="outline"
            disabled={page === data.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

function PaymentLinkCard({ link }: { link: PaymentLink }) {
  const handleCopy = async () => {
    await navigator.clipboard.writeText(link.checkout_url);
    toast.success('Link copied to clipboard');
  };

  return (
    <div className="border rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-semibold text-lg">{link.name}</h3>
          {link.description && (
            <p className="text-sm text-gray-600">{link.description}</p>
          )}
        </div>
        <Badge variant={link.is_active ? 'success' : 'secondary'}>
          {link.is_active ? 'Active' : 'Inactive'}
        </Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
        <div>
          <p className="text-xs text-gray-500">Amount</p>
          <p className="font-semibold">
            {link.is_amount_fixed
              ? formatCurrency(link.amount_fiat!, link.fiat_currency)
              : 'Variable'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Views</p>
          <p className="font-semibold">{link.view_count}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Payments</p>
          <p className="font-semibold">{link.payment_count}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Total Collected</p>
          <p className="font-semibold">
            {formatCurrency(link.total_collected_usd, 'USD')}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-3 text-sm">
        <span className="text-gray-500">Tokens:</span>
        <div className="flex gap-1">
          {link.accepted_tokens.map((token) => (
            <Badge key={token} variant="outline" className="text-xs">
              {token}
            </Badge>
          ))}
        </div>
      </div>

      <div className="flex justify-between items-center pt-3 border-t">
        <p className="text-xs text-gray-500">
          Created {formatDate(link.created_at)}
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={handleCopy}>
            <Copy className="w-4 h-4 mr-1" />
            Copy Link
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => window.open(link.checkout_url, '_blank')}
          >
            <ExternalLink className="w-4 h-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => window.location.href = `/payment-links/${link.id}/analytics`}
          >
            <BarChart3 className="w-4 h-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => window.location.href = `/payment-links/${link.id}/edit`}
          >
            <Edit className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
```

**`src/components/payment-links/CreatePaymentLinkForm.tsx`**

```typescript
import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useCreatePaymentLink } from '@/hooks/use-payment-links';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useNavigate } from 'react-router-dom';

const createPaymentLinkSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().optional(),
  amount_fiat: z.number().positive().optional(),
  is_amount_fixed: z.boolean(),
  accepted_tokens: z.array(z.string()).min(1, 'Select at least one token'),
  accepted_chains: z.array(z.string()).min(1, 'Select at least one chain'),
  success_url: z.string().url().optional().or(z.literal('')),
  cancel_url: z.string().url().optional().or(z.literal('')),
  is_single_use: z.boolean(),
  expires_at: z.string().optional(),
});

type CreatePaymentLinkFormData = z.infer<typeof createPaymentLinkSchema>;

export function CreatePaymentLinkForm() {
  const navigate = useNavigate();
  const createMutation = useCreatePaymentLink();

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<CreatePaymentLinkFormData>({
    resolver: zodResolver(createPaymentLinkSchema),
    defaultValues: {
      is_amount_fixed: true,
      is_single_use: false,
      accepted_tokens: ['USDC'],
      accepted_chains: ['polygon'],
    },
  });

  const isAmountFixed = watch('is_amount_fixed');

  const onSubmit = async (data: CreatePaymentLinkFormData) => {
    const input = {
      ...data,
      amount_fiat: isAmountFixed ? data.amount_fiat : undefined,
      success_url: data.success_url || undefined,
      cancel_url: data.cancel_url || undefined,
      expires_at: data.expires_at || undefined,
    };

    await createMutation.mutateAsync(input);
    navigate('/payment-links');
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-2xl">
      <div>
        <Label htmlFor="name">Link Name *</Label>
        <Input
          id="name"
          {...register('name')}
          placeholder="e.g., Monthly Subscription"
        />
        {errors.name && (
          <p className="text-sm text-red-500 mt-1">{errors.name.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          {...register('description')}
          placeholder="What is this payment for?"
          rows={3}
        />
      </div>

      <div>
        <div className="flex items-center space-x-2 mb-2">
          <Checkbox
            id="is_amount_fixed"
            checked={isAmountFixed}
            onCheckedChange={(checked) => setValue('is_amount_fixed', checked as boolean)}
          />
          <Label htmlFor="is_amount_fixed">Fixed amount</Label>
        </div>

        {isAmountFixed && (
          <div>
            <Label htmlFor="amount_fiat">Amount (USD) *</Label>
            <Input
              id="amount_fiat"
              type="number"
              step="0.01"
              {...register('amount_fiat', { valueAsNumber: true })}
              placeholder="0.00"
            />
            {errors.amount_fiat && (
              <p className="text-sm text-red-500 mt-1">{errors.amount_fiat.message}</p>
            )}
          </div>
        )}
      </div>

      <div>
        <Label>Accepted Tokens *</Label>
        <div className="grid grid-cols-3 gap-2 mt-2">
          {['USDC', 'USDT', 'XLM', 'ETH', 'MATIC'].map((token) => (
            <div key={token} className="flex items-center space-x-2">
              <Checkbox id={`token-${token}`} value={token} />
              <Label htmlFor={`token-${token}`}>{token}</Label>
            </div>
          ))}
        </div>
      </div>

      <div>
        <Label>Accepted Chains *</Label>
        <div className="grid grid-cols-3 gap-2 mt-2">
          {['stellar', 'polygon', 'ethereum', 'base', 'tron'].map((chain) => (
            <div key={chain} className="flex items-center space-x-2">
              <Checkbox id={`chain-${chain}`} value={chain} />
              <Label htmlFor={`chain-${chain}`} className="capitalize">
                {chain}
              </Label>
            </div>
          ))}
        </div>
      </div>

      <div>
        <Label htmlFor="success_url">Success Redirect URL</Label>
        <Input
          id="success_url"
          {...register('success_url')}
          type="url"
          placeholder="https://yoursite.com/success"
        />
      </div>

      <div>
        <Label htmlFor="cancel_url">Cancel Redirect URL</Label>
        <Input
          id="cancel_url"
          {...register('cancel_url')}
          type="url"
          placeholder="https://yoursite.com/cancel"
        />
      </div>

      <div className="flex items-center space-x-2">
        <Checkbox
          id="is_single_use"
          {...register('is_single_use')}
        />
        <Label htmlFor="is_single_use">Single use (deactivate after first payment)</Label>
      </div>

      <div>
        <Label htmlFor="expires_at">Expiration Date (Optional)</Label>
        <Input
          id="expires_at"
          type="datetime-local"
          {...register('expires_at')}
        />
      </div>

      <div className="flex gap-3">
        <Button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating...' : 'Create Payment Link'}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate('/payment-links')}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
```

---

## Invoice System Integration

### API Service

**`src/services/invoices.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  Invoice,
  CreateInvoiceInput,
  UpdateInvoiceInput,
  PaginatedResponse,
  InvoiceStatus,
} from '@/types/api.types';
import { v4 as uuidv4 } from 'uuid';

export class InvoicesService {
  private basePath = '/invoices';

  async createInvoice(input: CreateInvoiceInput): Promise<Invoice> {
    return apiClient.post<Invoice>(this.basePath, input, {
      idempotencyKey: uuidv4(),
    });
  }

  async listInvoices(params?: {
    page?: number;
    page_size?: number;
    status?: InvoiceStatus;
    customer_email?: string;
  }): Promise<PaginatedResponse<Invoice>> {
    return apiClient.get<PaginatedResponse<Invoice>>(this.basePath, { params });
  }

  async getInvoice(invoiceId: string): Promise<Invoice> {
    return apiClient.get<Invoice>(`${this.basePath}/${invoiceId}`);
  }

  async updateInvoice(invoiceId: string, input: UpdateInvoiceInput): Promise<Invoice> {
    return apiClient.patch<Invoice>(`${this.basePath}/${invoiceId}`, input);
  }

  async sendInvoice(invoiceId: string, message?: string): Promise<Invoice> {
    return apiClient.post<Invoice>(`${this.basePath}/${invoiceId}/send`, { message });
  }

  async sendReminder(invoiceId: string): Promise<void> {
    return apiClient.post<void>(`${this.basePath}/${invoiceId}/remind`);
  }

  async cancelInvoice(invoiceId: string): Promise<Invoice> {
    return apiClient.post<Invoice>(`${this.basePath}/${invoiceId}/cancel`);
  }

  async duplicateInvoice(invoiceId: string): Promise<Invoice> {
    return apiClient.post<Invoice>(`${this.basePath}/${invoiceId}/duplicate`);
  }

  calculateTotal(lineItems: { quantity: number; unit_price: number }[], tax = 0, discount = 0): number {
    const subtotal = lineItems.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
    return subtotal + tax - discount;
  }
}

export const invoicesService = new InvoicesService();
```

### React Query Hooks

**`src/hooks/use-invoices.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { invoicesService } from '@/services/invoices.service';
import { CreateInvoiceInput, UpdateInvoiceInput, InvoiceStatus } from '@/types/api.types';
import { toast } from 'sonner';

export const INVOICES_QUERY_KEY = 'invoices';

export function useInvoices(page = 1, pageSize = 20, status?: InvoiceStatus) {
  return useQuery({
    queryKey: [INVOICES_QUERY_KEY, { page, pageSize, status }],
    queryFn: () => invoicesService.listInvoices({ page, page_size: pageSize, status }),
  });
}

export function useInvoice(invoiceId: string) {
  return useQuery({
    queryKey: [INVOICES_QUERY_KEY, invoiceId],
    queryFn: () => invoicesService.getInvoice(invoiceId),
    enabled: !!invoiceId,
  });
}

export function useCreateInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateInvoiceInput) => invoicesService.createInvoice(input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY] });
      toast.success(`Invoice ${data.invoice_number} created`);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create invoice');
    },
  });
}

export function useUpdateInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ invoiceId, input }: { invoiceId: string; input: UpdateInvoiceInput }) =>
      invoicesService.updateInvoice(invoiceId, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY, data.id] });
      toast.success('Invoice updated');
    },
  });
}

export function useSendInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ invoiceId, message }: { invoiceId: string; message?: string }) =>
      invoicesService.sendInvoice(invoiceId, message),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY, data.id] });
      toast.success('Invoice sent successfully');
    },
  });
}

export function useCancelInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invoiceId: string) => invoicesService.cancelInvoice(invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [INVOICES_QUERY_KEY] });
      toast.success('Invoice cancelled');
    },
  });
}
```

### React Components

**`src/components/invoices/InvoicesList.tsx`**

```typescript
import React, { useState } from 'react';
import { useInvoices } from '@/hooks/use-invoices';
import { Invoice, InvoiceStatus } from '@/types/api.types';
import { formatCurrency, formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/select';
import { FileText, Send, Eye, Download } from 'lucide-react';

const STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: 'gray',
  sent: 'blue',
  viewed: 'purple',
  paid: 'green',
  overdue: 'red',
  cancelled: 'gray',
};

export function InvoicesList() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | undefined>();
  const { data, isLoading } = useInvoices(page, 20, statusFilter);

  if (isLoading) return <div>Loading invoices...</div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Invoices</h2>
        <div className="flex gap-3">
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as InvoiceStatus)}
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="paid">Paid</option>
            <option value="overdue">Overdue</option>
          </Select>
          <Button onClick={() => window.location.href = '/invoices/new'}>
            Create Invoice
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b">
              <th className="text-left p-3">Invoice #</th>
              <th className="text-left p-3">Customer</th>
              <th className="text-left p-3">Amount</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Due Date</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((invoice) => (
              <InvoiceRow key={invoice.id} invoice={invoice} />
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button
            variant="outline"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="py-2 px-4">
            Page {page} of {data.pages}
          </span>
          <Button
            variant="outline"
            disabled={page === data.pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

function InvoiceRow({ invoice }: { invoice: Invoice }) {
  const { mutate: sendInvoice } = useSendInvoice();

  return (
    <tr className="border-b hover:bg-gray-50">
      <td className="p-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-400" />
          <span className="font-mono">{invoice.invoice_number}</span>
        </div>
      </td>
      <td className="p-3">
        <div>
          <p className="font-medium">{invoice.customer_name || invoice.customer_email}</p>
          <p className="text-sm text-gray-500">{invoice.customer_email}</p>
        </div>
      </td>
      <td className="p-3">
        <span className="font-semibold">
          {formatCurrency(invoice.total, invoice.fiat_currency)}
        </span>
      </td>
      <td className="p-3">
        <Badge variant={STATUS_COLORS[invoice.status]}>
          {invoice.status.toUpperCase()}
        </Badge>
      </td>
      <td className="p-3">
        <span className={invoice.status === 'overdue' ? 'text-red-600 font-semibold' : ''}>
          {formatDate(invoice.due_date)}
        </span>
      </td>
      <td className="p-3">
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => window.location.href = `/invoices/${invoice.id}`}
          >
            <Eye className="w-4 h-4" />
          </Button>
          {invoice.status === 'draft' && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => sendInvoice({ invoiceId: invoice.id })}
            >
              <Send className="w-4 h-4" />
            </Button>
          )}
          {invoice.payment_url && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => window.open(invoice.payment_url, '_blank')}
            >
              Pay
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}
```

**`src/components/invoices/CreateInvoiceForm.tsx`**

```typescript
import React, { useState } from 'react';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useCreateInvoice } from '@/hooks/use-invoices';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { invoicesService } from '@/services/invoices.service';

const lineItemSchema = z.object({
  description: z.string().min(1, 'Description required'),
  quantity: z.number().positive(),
  unit_price: z.number().positive(),
});

const createInvoiceSchema = z.object({
  customer_email: z.string().email('Invalid email'),
  customer_name: z.string().optional(),
  customer_address: z.string().optional(),
  description: z.string().optional(),
  line_items: z.array(lineItemSchema).min(1, 'Add at least one line item'),
  tax: z.number().min(0),
  discount: z.number().min(0),
  due_date: z.string().min(1, 'Due date required'),
  accepted_tokens: z.array(z.string()).min(1),
  accepted_chains: z.array(z.string()).min(1),
  notes: z.string().optional(),
  terms: z.string().optional(),
  send_immediately: z.boolean(),
});

type CreateInvoiceFormData = z.infer<typeof createInvoiceSchema>;

export function CreateInvoiceForm() {
  const navigate = useNavigate();
  const createMutation = useCreateInvoice();

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<CreateInvoiceFormData>({
    resolver: zodResolver(createInvoiceSchema),
    defaultValues: {
      line_items: [{ description: '', quantity: 1, unit_price: 0 }],
      tax: 0,
      discount: 0,
      accepted_tokens: ['USDC'],
      accepted_chains: ['polygon'],
      send_immediately: false,
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'line_items',
  });

  const lineItems = watch('line_items');
  const tax = watch('tax');
  const discount = watch('discount');

  const total = invoicesService.calculateTotal(lineItems, tax, discount);

  const onSubmit = async (data: CreateInvoiceFormData) => {
    await createMutation.mutateAsync(data);
    navigate('/invoices');
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-4xl">
      <h2 className="text-2xl font-bold">Create Invoice</h2>

      {/* Customer Information */}
      <div className="space-y-4 border rounded-lg p-4">
        <h3 className="font-semibold">Customer Information</h3>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="customer_email">Customer Email *</Label>
            <Input
              id="customer_email"
              type="email"
              {...register('customer_email')}
              placeholder="customer@example.com"
            />
            {errors.customer_email && (
              <p className="text-sm text-red-500 mt-1">{errors.customer_email.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="customer_name">Customer Name</Label>
            <Input
              id="customer_name"
              {...register('customer_name')}
              placeholder="John Smith"
            />
          </div>
        </div>

        <div>
          <Label htmlFor="customer_address">Customer Address</Label>
          <Textarea
            id="customer_address"
            {...register('customer_address')}
            placeholder="123 Main St, City, State 12345"
            rows={2}
          />
        </div>
      </div>

      {/* Line Items */}
      <div className="space-y-4 border rounded-lg p-4">
        <div className="flex justify-between items-center">
          <h3 className="font-semibold">Line Items</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => append({ description: '', quantity: 1, unit_price: 0 })}
          >
            <Plus className="w-4 h-4 mr-1" />
            Add Item
          </Button>
        </div>

        <div className="space-y-3">
          {fields.map((field, index) => (
            <div key={field.id} className="grid grid-cols-12 gap-3 items-start">
              <div className="col-span-6">
                <Input
                  {...register(`line_items.${index}.description`)}
                  placeholder="Description"
                />
              </div>
              <div className="col-span-2">
                <Input
                  type="number"
                  {...register(`line_items.${index}.quantity`, { valueAsNumber: true })}
                  placeholder="Qty"
                />
              </div>
              <div className="col-span-3">
                <Input
                  type="number"
                  step="0.01"
                  {...register(`line_items.${index}.unit_price`, { valueAsNumber: true })}
                  placeholder="Unit Price"
                />
              </div>
              <div className="col-span-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => remove(index)}
                  disabled={fields.length === 1}
                >
                  <Trash2 className="w-4 h-4 text-red-500" />
                </Button>
              </div>
            </div>
          ))}
        </div>

        {/* Totals */}
        <div className="border-t pt-3 space-y-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="tax">Tax</Label>
              <Input
                id="tax"
                type="number"
                step="0.01"
                {...register('tax', { valueAsNumber: true })}
                placeholder="0.00"
              />
            </div>
            <div>
              <Label htmlFor="discount">Discount</Label>
              <Input
                id="discount"
                type="number"
                step="0.01"
                {...register('discount', { valueAsNumber: true })}
                placeholder="0.00"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <div className="text-right">
              <p className="text-sm text-gray-500">Subtotal</p>
              <p className="text-2xl font-bold">${total.toFixed(2)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Due Date */}
      <div>
        <Label htmlFor="due_date">Due Date *</Label>
        <Input
          id="due_date"
          type="date"
          {...register('due_date')}
        />
        {errors.due_date && (
          <p className="text-sm text-red-500 mt-1">{errors.due_date.message}</p>
        )}
      </div>

      {/* Notes & Terms */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="notes">Notes</Label>
          <Textarea
            id="notes"
            {...register('notes')}
            placeholder="Additional notes for customer"
            rows={3}
          />
        </div>
        <div>
          <Label htmlFor="terms">Payment Terms</Label>
          <Textarea
            id="terms"
            {...register('terms')}
            placeholder="Net 30, etc."
            rows={3}
          />
        </div>
      </div>

      {/* Send Option */}
      <div className="flex items-center space-x-2">
        <Checkbox
          id="send_immediately"
          {...register('send_immediately')}
        />
        <Label htmlFor="send_immediately">Send invoice immediately after creation</Label>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <Button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating...' : 'Create Invoice'}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate('/invoices')}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
```

---

## Subscriptions Integration

### API Service

**`src/services/subscriptions.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  SubscriptionPlan,
  Subscription,
  SubscriptionPayment,
  CreateSubscriptionPlanInput,
  CreateSubscriptionInput,
  PaginatedResponse,
  SubscriptionStatus,
} from '@/types/api.types';

export class SubscriptionsService {
  private basePath = '/subscriptions';

  // Plans
  async createPlan(input: CreateSubscriptionPlanInput): Promise<SubscriptionPlan> {
    return apiClient.post<SubscriptionPlan>(`${this.basePath}/plans`, input);
  }

  async listPlans(isActive?: boolean): Promise<PaginatedResponse<SubscriptionPlan>> {
    return apiClient.get<PaginatedResponse<SubscriptionPlan>>(`${this.basePath}/plans`, {
      params: { is_active: isActive },
    });
  }

  async getPlan(planId: string): Promise<SubscriptionPlan> {
    return apiClient.get<SubscriptionPlan>(`${this.basePath}/plans/${planId}`);
  }

  async updatePlan(planId: string, input: Partial<CreateSubscriptionPlanInput>): Promise<SubscriptionPlan> {
    return apiClient.patch<SubscriptionPlan>(`${this.basePath}/plans/${planId}`, input);
  }

  async deactivatePlan(planId: string): Promise<void> {
    return apiClient.delete<void>(`${this.basePath}/plans/${planId}`);
  }

  // Subscriptions
  async createSubscription(input: CreateSubscriptionInput): Promise<Subscription> {
    return apiClient.post<Subscription>(this.basePath, input);
  }

  async listSubscriptions(params?: {
    page?: number;
    page_size?: number;
    status?: SubscriptionStatus;
    plan_id?: string;
  }): Promise<PaginatedResponse<Subscription>> {
    return apiClient.get<PaginatedResponse<Subscription>>(this.basePath, { params });
  }

  async getSubscription(subscriptionId: string): Promise<Subscription> {
    return apiClient.get<Subscription>(`${this.basePath}/${subscriptionId}`);
  }

  async cancelSubscription(subscriptionId: string, cancelImmediately = false, reason?: string): Promise<Subscription> {
    return apiClient.post<Subscription>(`${this.basePath}/${subscriptionId}/cancel`, {
      cancel_immediately: cancelImmediately,
      reason,
    });
  }

  async pauseSubscription(subscriptionId: string): Promise<Subscription> {
    return apiClient.post<Subscription>(`${this.basePath}/${subscriptionId}/pause`);
  }

  async resumeSubscription(subscriptionId: string): Promise<Subscription> {
    return apiClient.post<Subscription>(`${this.basePath}/${subscriptionId}/resume`);
  }

  async getSubscriptionPayments(subscriptionId: string): Promise<PaginatedResponse<SubscriptionPayment>> {
    return apiClient.get<PaginatedResponse<SubscriptionPayment>>(`${this.basePath}/${subscriptionId}/payments`);
  }
}

export const subscriptionsService = new SubscriptionsService();
```

### React Query Hooks

**`src/hooks/use-subscriptions.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { subscriptionsService } from '@/services/subscriptions.service';
import { CreateSubscriptionPlanInput, CreateSubscriptionInput } from '@/types/api.types';
import { toast } from 'sonner';

export const SUBSCRIPTION_PLANS_QUERY_KEY = 'subscription-plans';
export const SUBSCRIPTIONS_QUERY_KEY = 'subscriptions';

// Plans
export function useSubscriptionPlans(isActive?: boolean) {
  return useQuery({
    queryKey: [SUBSCRIPTION_PLANS_QUERY_KEY, { isActive }],
    queryFn: () => subscriptionsService.listPlans(isActive),
  });
}

export function useSubscriptionPlan(planId: string) {
  return useQuery({
    queryKey: [SUBSCRIPTION_PLANS_QUERY_KEY, planId],
    queryFn: () => subscriptionsService.getPlan(planId),
    enabled: !!planId,
  });
}

export function useCreateSubscriptionPlan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateSubscriptionPlanInput) => subscriptionsService.createPlan(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [SUBSCRIPTION_PLANS_QUERY_KEY] });
      toast.success('Plan created successfully');
    },
  });
}

// Subscriptions
export function useSubscriptions(page = 1, pageSize = 20) {
  return useQuery({
    queryKey: [SUBSCRIPTIONS_QUERY_KEY, { page, pageSize }],
    queryFn: () => subscriptionsService.listSubscriptions({ page, page_size: pageSize }),
  });
}

export function useSubscription(subscriptionId: string) {
  return useQuery({
    queryKey: [SUBSCRIPTIONS_QUERY_KEY, subscriptionId],
    queryFn: () => subscriptionsService.getSubscription(subscriptionId),
    enabled: !!subscriptionId,
  });
}

export function useCreateSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateSubscriptionInput) => subscriptionsService.createSubscription(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [SUBSCRIPTIONS_QUERY_KEY] });
      toast.success('Subscription created');
    },
  });
}

export function useCancelSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ subscriptionId, immediate, reason }: { subscriptionId: string; immediate?: boolean; reason?: string }) =>
      subscriptionsService.cancelSubscription(subscriptionId, immediate, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [SUBSCRIPTIONS_QUERY_KEY] });
      toast.success('Subscription cancelled');
    },
  });
}
```

---

## Refunds Integration

### API Service

**`src/services/refunds.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  Refund,
  CreateRefundInput,
  PaginatedResponse,
  RefundStatus,
} from '@/types/api.types';

export class RefundsService {
  private basePath = '/refunds';

  async createRefund(input: CreateRefundInput): Promise<Refund> {
    return apiClient.post<Refund>(this.basePath, input);
  }

  async listRefunds(params?: {
    page?: number;
    page_size?: number;
    status?: RefundStatus;
    payment_session_id?: string;
  }): Promise<PaginatedResponse<Refund>> {
    return apiClient.get<PaginatedResponse<Refund>>(this.basePath, { params });
  }

  async getRefund(refundId: string): Promise<Refund> {
    return apiClient.get<Refund>(`${this.basePath}/${refundId}`);
  }

  async cancelRefund(refundId: string): Promise<Refund> {
    return apiClient.post<Refund>(`${this.basePath}/${refundId}/cancel`);
  }

  async retryRefund(refundId: string): Promise<Refund> {
    return apiClient.post<Refund>(`${this.basePath}/${refundId}/retry`);
  }
}

export const refundsService = new RefundsService();
```

### React Components

**`src/components/refunds/RefundDialog.tsx`**

```typescript
import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { refundsService } from '@/services/refunds.service';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { PaymentSession } from '@/types/api.types';
import { toast } from 'sonner';

const refundSchema = z.object({
  payment_session_id: z.string(),
  amount: z.number().positive().optional(),
  refund_address: z.string().min(1, 'Refund address required'),
  reason: z.string().optional(),
  is_full_refund: z.boolean(),
});

type RefundFormData = z.infer<typeof refundSchema>;

interface RefundDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  payment: PaymentSession;
}

export function RefundDialog({ open, onOpenChange, payment }: RefundDialogProps) {
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RefundFormData>({
    resolver: zodResolver(refundSchema),
    defaultValues: {
      payment_session_id: payment.id,
      is_full_refund: true,
    },
  });

  const isFullRefund = watch('is_full_refund');

  const createRefundMutation = useMutation({
    mutationFn: (input: { payment_session_id: string; amount?: number; refund_address: string; reason?: string }) =>
      refundsService.createRefund(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['refunds'] });
      queryClient.invalidateQueries({ queryKey: ['payments'] });
      toast.success('Refund initiated successfully');
      onOpenChange(false);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create refund');
    },
  });

  const onSubmit = (data: RefundFormData) => {
    createRefundMutation.mutate({
      payment_session_id: data.payment_session_id,
      amount: data.is_full_refund ? undefined : data.amount,
      refund_address: data.refund_address,
      reason: data.reason,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Process Refund</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <p className="text-sm text-gray-600">
              Payment Amount: <span className="font-semibold">${payment.amount_fiat}</span>
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="is_full_refund"
              {...register('is_full_refund')}
            />
            <Label htmlFor="is_full_refund">Full refund</Label>
          </div>

          {!isFullRefund && (
            <div>
              <Label htmlFor="amount">Refund Amount *</Label>
              <Input
                id="amount"
                type="number"
                step="0.01"
                max={payment.amount_fiat}
                {...register('amount', { valueAsNumber: true })}
                placeholder="0.00"
              />
              {errors.amount && (
                <p className="text-sm text-red-500 mt-1">{errors.amount.message}</p>
              )}
            </div>
          )}

          <div>
            <Label htmlFor="refund_address">Refund Address *</Label>
            <Input
              id="refund_address"
              {...register('refund_address')}
              placeholder="Customer's wallet address"
            />
            {errors.refund_address && (
              <p className="text-sm text-red-500 mt-1">{errors.refund_address.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="reason">Reason (Optional)</Label>
            <Textarea
              id="reason"
              {...register('reason')}
              placeholder="Why is this refund being processed?"
              rows={3}
            />
          </div>

          <div className="flex gap-3">
            <Button type="submit" disabled={createRefundMutation.isPending}>
              {createRefundMutation.isPending ? 'Processing...' : 'Process Refund'}
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

---

## Analytics Dashboard

### API Service

**`src/services/analytics.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  AnalyticsOverview,
  RevenueTimeSeries,
  ConversionMetrics,
} from '@/types/api.types';

export class AnalyticsService {
  private basePath = '/analytics';

  async getOverview(period: 'day' | 'week' | 'month' | 'year' = 'month'): Promise<AnalyticsOverview> {
    return apiClient.get<AnalyticsOverview>(`${this.basePath}/overview`, {
      params: { period },
    });
  }

  async getRevenue(period: 'day' | 'week' | 'month' | 'year' = 'month'): Promise<RevenueTimeSeries> {
    return apiClient.get<RevenueTimeSeries>(`${this.basePath}/revenue`, {
      params: { period },
    });
  }

  async getConversionMetrics(days = 30): Promise<ConversionMetrics> {
    return apiClient.get<ConversionMetrics>(`${this.basePath}/conversion`, {
      params: { days },
    });
  }

  async getChainAnalytics(days = 30) {
    return apiClient.get(`${this.basePath}/chains`, {
      params: { days },
    });
  }
}

export const analyticsService = new AnalyticsService();
```

### React Components

**`src/components/analytics/AnalyticsDashboard.tsx`**

```typescript
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsService } from '@/services/analytics.service';
import { Line, Pie, Bar } from 'react-chartjs-2';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Select } from '@/components/ui/select';
import { formatCurrency } from '@/lib/utils';
import { TrendingUp, TrendingDown, DollarSign, CreditCard, Target, Users } from 'lucide-react';

export function AnalyticsDashboard() {
  const [period, setPeriod] = useState<'day' | 'week' | 'month' | 'year'>('month');

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['analytics', 'overview', period],
    queryFn: () => analyticsService.getOverview(period),
  });

  const { data: revenue } = useQuery({
    queryKey: ['analytics', 'revenue', period],
    queryFn: () => analyticsService.getRevenue(period),
  });

  if (overviewLoading) return <div>Loading analytics...</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Analytics Dashboard</h1>
        <Select value={period} onValueChange={(value) => setPeriod(value as any)}>
          <option value="day">Today</option>
          <option value="week">This Week</option>
          <option value="month">This Month</option>
          <option value="year">This Year</option>
        </Select>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Volume"
          value={formatCurrency(overview?.payments.total_volume_usd || 0, 'USD')}
          change={overview?.volume_change_pct}
          icon={<DollarSign className="w-5 h-5" />}
        />
        <MetricCard
          title="Payments"
          value={overview?.payments.total_payments.toString() || '0'}
          change={overview?.payments_change_pct}
          icon={<CreditCard className="w-5 h-5" />}
        />
        <MetricCard
          title="Conversion Rate"
          value={`${overview?.payments.conversion_rate.toFixed(2)}%`}
          icon={<Target className="w-5 h-5" />}
        />
        <MetricCard
          title="Avg Payment"
          value={formatCurrency(overview?.payments.avg_payment_usd || 0, 'USD')}
          icon={<DollarSign className="w-5 h-5" />}
        />
      </div>

      {/* Revenue Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Revenue Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {revenue && (
            <Line
              data={{
                labels: revenue.data.map(d => new Date(d.date).toLocaleDateString()),
                datasets: [
                  {
                    label: 'Revenue (USD)',
                    data: revenue.data.map(d => d.volume_usd),
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: {
                    display: false,
                  },
                },
              }}
              height={300}
            />
          )}
        </CardContent>
      </Card>

      {/* Token & Chain Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Volume by Token</CardTitle>
          </CardHeader>
          <CardContent>
            {overview && (
              <Pie
                data={{
                  labels: overview.volume_by_token.map(t => t.token),
                  datasets: [
                    {
                      data: overview.volume_by_token.map(t => t.volume_usd),
                      backgroundColor: [
                        'rgb(59, 130, 246)',
                        'rgb(16, 185, 129)',
                        'rgb(251, 191, 36)',
                        'rgb(239, 68, 68)',
                        'rgb(139, 92, 246)',
                      ],
                    },
                  ],
                }}
                height={250}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Volume by Chain</CardTitle>
          </CardHeader>
          <CardContent>
            {overview && (
              <Bar
                data={{
                  labels: overview.volume_by_chain.map(c => c.chain.toUpperCase()),
                  datasets: [
                    {
                      label: 'Volume (USD)',
                      data: overview.volume_by_chain.map(c => c.volume_usd),
                      backgroundColor: 'rgb(59, 130, 246)',
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                }}
                height={250}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Subscription MRR */}
      {overview && overview.subscription_mrr > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Subscription Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-500">Monthly Recurring Revenue</p>
                <p className="text-2xl font-bold">{formatCurrency(overview.subscription_mrr, 'USD')}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Active Subscriptions</p>
                <p className="text-2xl font-bold">{overview.active_subscriptions}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">New This Period</p>
                <p className="text-2xl font-bold text-green-600">+{overview.new_subscriptions}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Churned</p>
                <p className="text-2xl font-bold text-red-600">-{overview.churned_subscriptions}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricCard({ title, value, change, icon }: {
  title: string;
  value: string;
  change?: number;
  icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex justify-between items-start mb-2">
          <p className="text-sm text-gray-500">{title}</p>
          <div className="text-gray-400">{icon}</div>
        </div>
        <p className="text-2xl font-bold mb-1">{value}</p>
        {change !== undefined && (
          <div className="flex items-center text-sm">
            {change >= 0 ? (
              <>
                <TrendingUp className="w-4 h-4 text-green-500 mr-1" />
                <span className="text-green-500">+{change.toFixed(1)}%</span>
              </>
            ) : (
              <>
                <TrendingDown className="w-4 h-4 text-red-500 mr-1" />
                <span className="text-red-500">{change.toFixed(1)}%</span>
              </>
            )}
            <span className="text-gray-500 ml-1">vs last period</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

---

## Team Management Integration

### API Service

**`src/services/team.service.ts`**

```typescript
import { apiClient } from '@/lib/api-client';
import {
  TeamMember,
  InviteTeamMemberInput,
  UpdateTeamMemberInput,
  RolePermissions,
  PaginatedResponse,
} from '@/types/api.types';

export class TeamService {
  private basePath = '/team';

  async inviteTeamMember(input: InviteTeamMemberInput): Promise<TeamMember> {
    return apiClient.post<TeamMember>(`${this.basePath}/invite`, input);
  }

  async listTeamMembers(): Promise<PaginatedResponse<TeamMember>> {
    return apiClient.get<PaginatedResponse<TeamMember>>(this.basePath);
  }

  async getTeamMember(memberId: string): Promise<TeamMember> {
    return apiClient.get<TeamMember>(`${this.basePath}/${memberId}`);
  }

  async updateTeamMember(memberId: string, input: UpdateTeamMemberInput): Promise<TeamMember> {
    return apiClient.patch<TeamMember>(`${this.basePath}/${memberId}`, input);
  }

  async removeTeamMember(memberId: string): Promise<void> {
    return apiClient.delete<void>(`${this.basePath}/${memberId}`);
  }

  async resendInvite(memberId: string): Promise<void> {
    return apiClient.post<void>(`${this.basePath}/${memberId}/resend-invite`);
  }

  async getRolePermissions(): Promise<RolePermissions[]> {
    return apiClient.get<RolePermissions[]>(`${this.basePath}/roles/permissions`);
  }
}

export const teamService = new TeamService();
```

### React Components

**`src/components/team/TeamMembersList.tsx`**

```typescript
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { teamService } from '@/services/team.service';
import { TeamMember, MerchantRole } from '@/types/api.types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/select';
import { UserPlus, Mail, Trash2, MoreVertical } from 'lucide-react';
import { toast } from 'sonner';
import { InviteTeamMemberDialog } from './InviteTeamMemberDialog';

const ROLE_COLORS: Record<MerchantRole, string> = {
  owner: 'purple',
  admin: 'blue',
  developer: 'green',
  finance: 'yellow',
  viewer: 'gray',
};

export function TeamMembersList() {
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: team, isLoading } = useQuery({
    queryKey: ['team'],
    queryFn: () => teamService.listTeamMembers(),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => teamService.removeTeamMember(memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team'] });
      toast.success('Team member removed');
    },
  });

  const resendInviteMutation = useMutation({
    mutationFn: (memberId: string) => teamService.resendInvite(memberId),
    onSuccess: () => {
      toast.success('Invitation resent');
    },
  });

  if (isLoading) return <div>Loading team members...</div>;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Team Members</h2>
        <Button onClick={() => setInviteDialogOpen(true)}>
          <UserPlus className="w-4 h-4 mr-2" />
          Invite Member
        </Button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b">
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Email</th>
              <th className="text-left p-3">Role</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {team?.items.map((member) => (
              <tr key={member.id} className="border-b hover:bg-gray-50">
                <td className="p-3">
                  <p className="font-medium">{member.name || 'Unnamed'}</p>
                </td>
                <td className="p-3">{member.email}</td>
                <td className="p-3">
                  <Badge variant={ROLE_COLORS[member.role]}>
                    {member.role.toUpperCase()}
                  </Badge>
                </td>
                <td className="p-3">
                  {member.invite_pending ? (
                    <Badge variant="warning">Pending Invite</Badge>
                  ) : member.is_active ? (
                    <Badge variant="success">Active</Badge>
                  ) : (
                    <Badge variant="secondary">Inactive</Badge>
                  )}
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    {member.invite_pending && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => resendInviteMutation.mutate(member.id)}
                      >
                        <Mail className="w-4 h-4" />
                      </Button>
                    )}
                    {member.role !== 'owner' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (confirm('Remove this team member?')) {
                            removeMemberMutation.mutate(member.id);
                          }
                        }}
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <InviteTeamMemberDialog
        open={inviteDialogOpen}
        onOpenChange={setInviteDialogOpen}
      />
    </div>
  );
}
```

---

## Webhook Handler Setup

### Backend Webhook Receiver

**`src/utils/webhook-handler.ts`**

```typescript
import crypto from 'crypto';
import { PaymentSession, Invoice, Subscription, Refund } from '@/types/api.types';

export interface WebhookEvent {
  event: string;
  session_id?: string;
  invoice_id?: string;
  subscription_id?: string;
  refund_id?: string;
  [key: string]: any;
}

export function verifyWebhookSignature(payload: string, signature: string, secret: string): boolean {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(`sha256=${expectedSignature}`),
    Buffer.from(signature)
  );
}

export class WebhookHandler {
  async handleEvent(event: WebhookEvent): Promise<void> {
    console.log(`Processing webhook event: ${event.event}`);

    switch (event.event) {
      case 'payment.created':
        await this.handlePaymentCreated(event);
        break;
      case 'payment.confirmed':
        await this.handlePaymentConfirmed(event);
        break;
      case 'payment.failed':
        await this.handlePaymentFailed(event);
        break;
      case 'invoice.paid':
        await this.handleInvoicePaid(event);
        break;
      case 'invoice.overdue':
        await this.handleInvoiceOverdue(event);
        break;
      case 'subscription.activated':
        await this.handleSubscriptionActivated(event);
        break;
      case 'subscription.renewed':
        await this.handleSubscriptionRenewed(event);
        break;
      case 'subscription.payment_failed':
        await this.handleSubscriptionPaymentFailed(event);
        break;
      case 'subscription.cancelled':
        await this.handleSubscriptionCancelled(event);
        break;
      case 'refund.completed':
        await this.handleRefundCompleted(event);
        break;
      default:
        console.log(`Unhandled event type: ${event.event}`);
    }
  }

  private async handlePaymentCreated(event: WebhookEvent): Promise<void> {
    // Update internal records
    // Send notification to merchant
  }

  private async handlePaymentConfirmed(event: WebhookEvent): Promise<void> {
    // Fulfill order
    // Update subscription status if applicable
    // Send receipt email
  }

  private async handlePaymentFailed(event: WebhookEvent): Promise<void> {
    // Log failure
    // Notify customer
    // Retry logic if subscription
  }

  private async handleInvoicePaid(event: WebhookEvent): Promise<void> {
    // Mark invoice as paid in internal system
    // Trigger accounting sync
    // Send thank you email
  }

  private async handleInvoiceOverdue(event: WebhookEvent): Promise<void> {
    // Send reminder email
    // Escalate to merchant dashboard
  }

  private async handleSubscriptionActivated(event: WebhookEvent): Promise<void> {
    // Grant access to service
    // Send welcome email
  }

  private async handleSubscriptionRenewed(event: WebhookEvent): Promise<void> {
    // Extend access period
    // Send renewal confirmation
  }

  private async handleSubscriptionPaymentFailed(event: WebhookEvent): Promise<void> {
    // Send payment failed notification
    // Trigger retry schedule
  }

  private async handleSubscriptionCancelled(event: WebhookEvent): Promise<void> {
    // Revoke access at period end
    // Send cancellation confirmation
  }

  private async handleRefundCompleted(event: WebhookEvent): Promise<void> {
    // Update order status
    // Send refund confirmation
  }
}

export const webhookHandler = new WebhookHandler();
```

### Express.js Webhook Endpoint

**`server/routes/webhooks.ts`**

```typescript
import express, { Request, Response } from 'express';
import { verifyWebhookSignature, webhookHandler } from '../utils/webhook-handler';

const router = express.Router();

router.post('/dari', async (req: Request, res: Response) => {
  const signature = req.headers['x-dari-signature'] as string;
  const payload = JSON.stringify(req.body);

  // Verify signature
  const webhookSecret = process.env.DARI_WEBHOOK_SECRET!;
  if (!verifyWebhookSignature(payload, signature, webhookSecret)) {
    console.error('Invalid webhook signature');
    return res.status(403).json({ error: 'Invalid signature' });
  }

  // Process event
  try {
    await webhookHandler.handleEvent(req.body);
    res.status(200).json({ received: true });
  } catch (error) {
    console.error('Webhook processing error:', error);
    res.status(500).json({ error: 'Processing failed' });
  }
});

export default router;
```

---

## State Management

### Zustand Store Example

**`src/stores/merchant-store.ts`**

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface MerchantState {
  apiKey: string | null;
  merchantId: string | null;
  merchantName: string | null;
  email: string | null;
  role: string | null;
  setMerchant: (data: {
    apiKey: string;
    merchantId: string;
    merchantName: string;
    email: string;
    role: string;
  }) => void;
  clearMerchant: () => void;
}

export const useMerchantStore = create<MerchantState>()(
  persist(
    (set) => ({
      apiKey: null,
      merchantId: null,
      merchantName: null,
      email: null,
      role: null,
      setMerchant: (data) => set(data),
      clearMerchant: () =>
        set({
          apiKey: null,
          merchantId: null,
          merchantName: null,
          email: null,
          role: null,
        }),
    }),
    {
      name: 'dari-merchant-store',
    }
  )
);
```

---

## UI Components Library

### Installation

```bash
# shadcn/ui (recommended)
npx shadcn-ui@latest init

# Or Material-UI
npm install @mui/material @emotion/react @emotion/styled

# Chart libraries
npm install chart.js react-chartjs-2
```

### Required Components

1. **Button** - Actions and submissions
2. **Input** - Form fields
3. **Select** - Dropdowns
4. **Checkbox** - Boolean inputs
5. **Badge** - Status indicators
6. **Card** - Content containers
7. **Dialog/Modal** - Overlays
8. **Table** - Data display
9. **Pagination** - List navigation
10. **Toast/Snackbar** - Notifications

---

## Testing Strategy

### Unit Tests

**`src/services/__tests__/payment-links.service.test.ts`**

```typescript
import { paymentLinksService } from '../payment-links.service';
import { apiClient } from '@/lib/api-client';

jest.mock('@/lib/api-client');

describe('PaymentLinksService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should create a payment link', async () => {
    const mockLink = {
      id: 'link_123',
      name: 'Test Link',
      amount_fiat: 100,
      checkout_url: 'https://example.com/pay/link_123',
    };

    (apiClient.post as jest.Mock).mockResolvedValue(mockLink);

    const result = await paymentLinksService.createPaymentLink({
      name: 'Test Link',
      amount_fiat: 100,
      accepted_tokens: ['USDC'],
      accepted_chains: ['polygon'],
    });

    expect(result).toEqual(mockLink);
    expect(apiClient.post).toHaveBeenCalledWith(
      '/payment-links',
      expect.objectContaining({ name: 'Test Link' }),
      expect.objectContaining({ idempotencyKey: expect.any(String) })
    );
  });
});
```

### Integration Tests

**`src/components/__tests__/PaymentLinksList.test.tsx`**

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PaymentLinksList } from '../payment-links/PaymentLinksList';
import { paymentLinksService } from '@/services/payment-links.service';

jest.mock('@/services/payment-links.service');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe('PaymentLinksList', () => {
  it('renders payment links', async () => {
    const mockLinks = {
      items: [
        {
          id: 'link_1',
          name: 'Test Link 1',
          amount_fiat: 100,
          view_count: 10,
          payment_count: 5,
        },
      ],
      total: 1,
      page: 1,
      pages: 1,
    };

    (paymentLinksService.listPaymentLinks as jest.Mock).mockResolvedValue(mockLinks);

    render(<PaymentLinksList />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText('Test Link 1')).toBeInTheDocument();
      expect(screen.getByText('10')).toBeInTheDocument(); // Views
      expect(screen.getByText('5')).toBeInTheDocument(); // Payments
    });
  });
});
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] Update API base URL in `.env`
- [ ] Set webhook URL in merchant settings
- [ ] Configure webhook secret
- [ ] Test all API endpoints with Postman
- [ ] Run unit and integration tests
- [ ] Build production bundle: `npm run build`
- [ ] Test production build locally
- [ ] Set up error tracking (Sentry)
- [ ] Configure analytics (Google Analytics)

### Post-Deployment

- [ ] Verify API connectivity
- [ ] Test webhook delivery
- [ ] Monitor error logs
- [ ] Check analytics tracking
- [ ] Test payment flows end-to-end
- [ ] Verify all enterprise features functional

### Environment Variables

```bash
# .env.production
REACT_APP_API_URL=https://api.dariforbusiness.com
REACT_APP_WEBHOOK_SECRET=whsec_your_production_secret
REACT_APP_ENABLE_ANALYTICS=true
REACT_APP_SENTRY_DSN=your_sentry_dsn
```

---

**End of Frontend Upgrade Guide**

*Version 2.0.0 | March 4, 2026* 
