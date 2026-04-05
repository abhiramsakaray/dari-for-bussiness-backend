# Frontend Changes V5 — Refunds, Trials & Recurring Payments

## New TypeScript Types

```typescript
// ============= REFUNDS =============

interface RefundEligibility {
  eligible: boolean;
  payment_session_id: string;
  max_refundable: number;
  already_refunded: number;
  merchant_balance: number;
  sufficient_balance: boolean;
  settlement_status: "in_platform" | "settled_external" | "partially_settled";
  message: string;
  can_queue: boolean;
  can_force_external: boolean;
}

interface RefundCreate {
  payment_session_id: string;
  amount?: number;            // null = full refund
  refund_address: string;
  reason?: string;
  force?: boolean;            // Force refund via external wallet (when settled externally)
  queue_if_insufficient?: boolean; // Queue for up to 7 days if balance too low
}

interface RefundResponse {
  id: string;
  payment_session_id: string;
  amount: number;
  token: string;
  chain: string;
  refund_address: string;
  status: "pending" | "processing" | "completed" | "failed" | "queued" | "insufficient_funds";
  tx_hash?: string;
  reason?: string;
  refund_source?: "platform_balance" | "external_wallet";
  settlement_status?: "in_platform" | "settled_external" | "partially_settled";
  merchant_balance_at_request?: number;
  failure_reason?: string;
  queued_until?: string;       // ISO datetime — refund auto-cancels after this
  created_at: string;
  processed_at?: string;
  completed_at?: string;
}

// ============= SUBSCRIPTIONS =============

type TrialType = "free" | "reduced_price";
type SubscriptionInterval = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";

interface SubscriptionPlanCreate {
  name: string;
  description?: string;
  amount: number;
  fiat_currency?: string;     // default "USD"
  interval: SubscriptionInterval;
  interval_count?: number;    // default 1
  trial_days?: number;        // default 0
  trial_type?: TrialType;     // default "free"
  trial_price?: number;       // only for "reduced_price"
  setup_fee?: number;         // one-time charge, default 0
  max_billing_cycles?: number; // null = unlimited
  accepted_tokens?: string[];
  accepted_chains?: string[];
  features?: string[];
  metadata?: Record<string, any>;
}

interface SubscriptionPlanResponse extends SubscriptionPlanCreate {
  id: string;
  is_active: boolean;
  subscriber_count: number;
  subscribe_url: string | null; // Public URL for customers to subscribe
  created_at: string;
}

interface SubscriptionCreate {
  plan_id: string;
  customer_email: string;
  customer_name?: string;
  customer_id?: string;
  customer_wallet_address?: string; // Customer wallet for auto-billing
  customer_chain?: string;
  customer_token?: string;
  skip_trial?: boolean;       // default false
  custom_trial_days?: number; // override plan's trial_days
  metadata?: Record<string, any>;
}

interface SubscriptionResponse {
  id: string;
  plan_id: string;
  plan_name: string;
  customer_email: string;
  customer_name?: string;
  customer_id?: string;
  status: "active" | "paused" | "cancelled" | "past_due" | "trialing";
  current_period_start: string;
  current_period_end: string;
  // Trial info
  trial_start?: string;
  trial_end?: string;
  trial_type?: TrialType;
  is_in_trial: boolean;
  trial_days_remaining?: number;
  // Payment stats
  total_payments_collected: number;
  total_revenue?: number;
  next_payment_at?: string;
  next_payment_url?: string;
  next_payment_amount?: number;
  // Customer payment method
  customer_wallet_address?: string;
  customer_chain?: string;
  customer_token?: string;
  has_payment_method: boolean;
  // Cancellation
  cancel_at?: string;
  cancelled_at?: string;
  created_at: string;
}

interface SubscriptionPayment {
  id: string;
  period_start: string;
  period_end: string;
  amount: number;
  fiat_currency: string;
  status: "created" | "pending" | "paid" | "expired" | "failed";
  paid_at?: string;
  payment_session_id?: string;
  created_at: string;
}
```

---

## New API Endpoints

### Refund Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/refunds/eligibility/{payment_session_id}` | Check if refund is possible & merchant balance |
| `POST` | `/refunds` | Create refund (with `force` / `queue_if_insufficient` options) |
| `POST` | `/refunds/{id}/cancel` | Cancel a pending/queued refund |
| `POST` | `/refunds/{id}/retry` | Retry a failed/insufficient_funds refund |
| `POST` | `/refunds/process-queued` | Batch-process all queued refunds |

### Subscription Endpoints (new)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/subscriptions/{id}/extend-trial` | Extend trial period |
| `POST` | `/subscriptions/{id}/end-trial` | Convert trial to paid immediately |
| `PUT`  | `/subscriptions/{id}/payment-method` | Set/update customer payment method |
| `POST` | `/subscriptions/{id}/collect-payment` | Trigger payment collection |
| `POST` | `/subscriptions/{id}/renew` | Advance to next billing cycle |

### Public Subscription Checkout (no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/subscribe/{plan_id}` | Public HTML page — customers see plan details & subscribe |
| `POST` | `/subscribe/{plan_id}` | Creates subscription + payment session, returns `checkout_url` |

When a plan is created or fetched, the response includes `subscribe_url` (e.g. `https://api.chainpe.com/subscribe/plan_xxxx`). Share this link with customers — they see a branded page with plan name, price, trial info, and a form to enter email/name. On submit, a subscription is created, a payment session is generated, and the customer is redirected to the standard checkout page.

The `POST /subscribe/{plan_id}` response:
```json
{
  "subscription_id": "sub_xxxx",
  "status": "trialing",
  "checkout_url": "/checkout/sess_xxxx",
  "message": "Subscription created. Complete payment to activate."
}
```

---

## API Service Methods

Add these to your API service (e.g., `chainpe.ts` or a dedicated service file):

```typescript
// ============= REFUND SERVICE =============

export const refundService = {
  /** Pre-flight check: balance, settlement, options */
  checkEligibility: (paymentSessionId: string) =>
    api.get<RefundEligibility>(`/refunds/eligibility/${paymentSessionId}`),

  /** Create refund */
  create: (data: RefundCreate) =>
    api.post<RefundResponse>("/refunds", data),

  /** List merchant refunds */
  list: (params?: { status?: string; skip?: number; limit?: number }) =>
    api.get<RefundResponse[]>("/refunds", { params }),

  /** Cancel a pending/queued refund */
  cancel: (refundId: string) =>
    api.post<RefundResponse>(`/refunds/${refundId}/cancel`),

  /** Retry a failed refund */
  retry: (refundId: string) =>
    api.post<RefundResponse>(`/refunds/${refundId}/retry`),

  /** Process all queued refunds (admin/cron) */
  processQueued: () =>
    api.post("/refunds/process-queued"),
};

// ============= SUBSCRIPTION SERVICE =============

export const subscriptionService = {
  // Plans
  createPlan: (data: SubscriptionPlanCreate) =>
    api.post<SubscriptionPlanResponse>("/subscriptions/plans", data),

  listPlans: () =>
    api.get<SubscriptionPlanResponse[]>("/subscriptions/plans"),

  getPlan: (planId: string) =>
    api.get<SubscriptionPlanResponse>(`/subscriptions/plans/${planId}`),

  updatePlan: (planId: string, data: Partial<SubscriptionPlanCreate>) =>
    api.put<SubscriptionPlanResponse>(`/subscriptions/plans/${planId}`, data),

  // Subscriptions
  create: (data: SubscriptionCreate) =>
    api.post<SubscriptionResponse>("/subscriptions", data),

  get: (subscriptionId: string) =>
    api.get<SubscriptionResponse>(`/subscriptions/${subscriptionId}`),

  list: (params?: { status?: string; skip?: number; limit?: number }) =>
    api.get<SubscriptionResponse[]>("/subscriptions", { params }),

  cancel: (subscriptionId: string, data?: { cancel_at_period_end?: boolean }) =>
    api.post(`/subscriptions/${subscriptionId}/cancel`, data),

  pause: (subscriptionId: string) =>
    api.post(`/subscriptions/${subscriptionId}/pause`),

  resume: (subscriptionId: string) =>
    api.post(`/subscriptions/${subscriptionId}/resume`),

  // Trial management
  extendTrial: (subscriptionId: string, extraDays: number) =>
    api.post(`/subscriptions/${subscriptionId}/extend-trial`, { extra_days: extraDays }),

  endTrial: (subscriptionId: string) =>
    api.post(`/subscriptions/${subscriptionId}/end-trial`),

  // Payment method
  updatePaymentMethod: (subscriptionId: string, data: {
    wallet_address: string;
    chain: string;
    token: string;
  }) => api.put(`/subscriptions/${subscriptionId}/payment-method`, data),

  // Payment collection
  collectPayment: (subscriptionId: string) =>
    api.post(`/subscriptions/${subscriptionId}/collect-payment`),

  renew: (subscriptionId: string) =>
    api.post(`/subscriptions/${subscriptionId}/renew`),

  // Payment history
  listPayments: (subscriptionId: string) =>
    api.get<SubscriptionPayment[]>(`/subscriptions/${subscriptionId}/payments`),
};
```

---

## React Component Examples

### 1. Refund with Balance Check

```tsx
import { useState, useEffect } from "react";
import { refundService } from "../services/api";

interface RefundFormProps {
  paymentSessionId: string;
  payerWallet: string;
  onComplete: () => void;
}

export function RefundForm({ paymentSessionId, payerWallet, onComplete }: RefundFormProps) {
  const [eligibility, setEligibility] = useState<RefundEligibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [refundResult, setRefundResult] = useState<RefundResponse | null>(null);

  // Step 1: Check eligibility on mount
  useEffect(() => {
    refundService.checkEligibility(paymentSessionId)
      .then(res => {
        setEligibility(res.data);
        setAmount(String(res.data.max_refundable));
      })
      .catch(() => setError("Failed to check refund eligibility"))
      .finally(() => setLoading(false));
  }, [paymentSessionId]);

  const handleSubmit = async (force = false, queue = false) => {
    setSubmitting(true);
    setError("");
    try {
      const res = await refundService.create({
        payment_session_id: paymentSessionId,
        amount: parseFloat(amount),
        refund_address: payerWallet,
        reason,
        force,
        queue_if_insufficient: queue,
      });
      setRefundResult(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Refund failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div>Checking refund eligibility...</div>;

  // Show result after submission
  if (refundResult) {
    return (
      <div style={{ padding: 20, border: "1px solid #e0e0e0", borderRadius: 8 }}>
        <h3>Refund {refundResult.status === "queued" ? "Queued" : "Created"}</h3>
        <p><strong>ID:</strong> {refundResult.id}</p>
        <p><strong>Status:</strong> {refundResult.status}</p>
        <p><strong>Amount:</strong> {refundResult.amount} {refundResult.token}</p>
        {refundResult.status === "queued" && (
          <p style={{ color: "#f59e0b" }}>
            ⏳ Refund queued. Will auto-process when funds are available
            (expires {new Date(refundResult.queued_until!).toLocaleDateString()}).
          </p>
        )}
        {refundResult.refund_source === "external_wallet" && (
          <p style={{ color: "#3b82f6" }}>
            💳 Refund will be processed from your external wallet.
          </p>
        )}
        <button onClick={onComplete}>Done</button>
      </div>
    );
  }

  return (
    <div style={{ padding: 20, border: "1px solid #e0e0e0", borderRadius: 8 }}>
      <h3>Issue Refund</h3>

      {/* Eligibility Info */}
      {eligibility && (
        <div style={{
          background: eligibility.sufficient_balance ? "#ecfdf5" : "#fef2f2",
          padding: 12, borderRadius: 6, marginBottom: 16
        }}>
          <p><strong>Settlement:</strong> {formatSettlement(eligibility.settlement_status)}</p>
          <p><strong>Your Balance:</strong> ${eligibility.merchant_balance.toFixed(2)}</p>
          <p><strong>Max Refundable:</strong> ${eligibility.max_refundable.toFixed(2)}</p>
          {eligibility.already_refunded > 0 && (
            <p><strong>Already Refunded:</strong> ${eligibility.already_refunded.toFixed(2)}</p>
          )}
          <p>{eligibility.message}</p>
        </div>
      )}

      {error && <p style={{ color: "red" }}>{error}</p>}

      <div style={{ marginBottom: 12 }}>
        <label>Amount</label>
        <input
          type="number"
          value={amount}
          onChange={e => setAmount(e.target.value)}
          max={eligibility?.max_refundable}
          step="0.01"
          style={{ width: "100%", padding: 8 }}
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <label>Reason (optional)</label>
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          style={{ width: "100%", padding: 8 }}
        />
      </div>

      {/* Action buttons based on eligibility */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {eligibility?.sufficient_balance && (
          <button
            onClick={() => handleSubmit(false, false)}
            disabled={submitting}
            style={{ background: "#10b981", color: "#fff", padding: "8px 16px", border: "none", borderRadius: 4 }}
          >
            {submitting ? "Processing..." : "Refund from Balance"}
          </button>
        )}

        {eligibility && !eligibility.sufficient_balance && eligibility.can_queue && (
          <button
            onClick={() => handleSubmit(false, true)}
            disabled={submitting}
            style={{ background: "#f59e0b", color: "#fff", padding: "8px 16px", border: "none", borderRadius: 4 }}
          >
            {submitting ? "Processing..." : "Queue Refund (7 days)"}
          </button>
        )}

        {eligibility?.can_force_external && (
          <button
            onClick={() => handleSubmit(true, false)}
            disabled={submitting}
            style={{ background: "#3b82f6", color: "#fff", padding: "8px 16px", border: "none", borderRadius: 4 }}
          >
            {submitting ? "Processing..." : "Refund via External Wallet"}
          </button>
        )}

        {!eligibility?.eligible && (
          <p style={{ color: "#ef4444" }}>
            Refund not available: {eligibility?.message}
          </p>
        )}
      </div>
    </div>
  );
}

function formatSettlement(status: string): string {
  switch (status) {
    case "in_platform": return "Funds in ChainPe";
    case "settled_external": return "Settled to external wallet";
    case "partially_settled": return "Partially settled";
    default: return status;
  }
}
```

### 2. Subscription Plan with Trial Config

```tsx
import { useState } from "react";
import { subscriptionService } from "../services/api";

export function CreatePlanForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState<SubscriptionPlanCreate>({
    name: "",
    amount: 0,
    interval: "monthly",
    trial_days: 0,
    trial_type: "free",
    trial_price: undefined,
    setup_fee: 0,
    max_billing_cycles: undefined,
    features: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const update = (partial: Partial<SubscriptionPlanCreate>) =>
    setForm(prev => ({ ...prev, ...partial }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await subscriptionService.createPlan(form);
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create plan");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 500 }}>
      <h3>Create Subscription Plan</h3>
      {error && <p style={{ color: "red" }}>{error}</p>}

      {/* Basic info */}
      <div style={{ marginBottom: 12 }}>
        <label>Plan Name</label>
        <input value={form.name} onChange={e => update({ name: e.target.value })} required />
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label>Price</label>
          <input type="number" value={form.amount} onChange={e => update({ amount: +e.target.value })} min={0} step="0.01" required />
        </div>
        <div style={{ flex: 1 }}>
          <label>Interval</label>
          <select value={form.interval} onChange={e => update({ interval: e.target.value as SubscriptionInterval })}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="yearly">Yearly</option>
          </select>
        </div>
      </div>

      {/* Trial config */}
      <fieldset style={{ border: "1px solid #e0e0e0", padding: 12, borderRadius: 6, marginBottom: 12 }}>
        <legend>Free Trial</legend>
        <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
          <div style={{ flex: 1 }}>
            <label>Trial Days</label>
            <input type="number" value={form.trial_days} onChange={e => update({ trial_days: +e.target.value })} min={0} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Trial Type</label>
            <select value={form.trial_type} onChange={e => update({ trial_type: e.target.value as TrialType })}>
              <option value="free">Free</option>
              <option value="reduced_price">Reduced Price</option>
            </select>
          </div>
        </div>
        {form.trial_type === "reduced_price" && (
          <div>
            <label>Trial Price</label>
            <input
              type="number"
              value={form.trial_price ?? ""}
              onChange={e => update({ trial_price: e.target.value ? +e.target.value : undefined })}
              min={0}
              step="0.01"
              placeholder="e.g., 4.99"
            />
          </div>
        )}
      </fieldset>

      {/* Advanced */}
      <fieldset style={{ border: "1px solid #e0e0e0", padding: 12, borderRadius: 6, marginBottom: 12 }}>
        <legend>Advanced</legend>
        <div style={{ marginBottom: 8 }}>
          <label>Setup Fee (one-time)</label>
          <input type="number" value={form.setup_fee} onChange={e => update({ setup_fee: +e.target.value })} min={0} step="0.01" />
        </div>
        <div>
          <label>Max Billing Cycles (leave empty for unlimited)</label>
          <input
            type="number"
            value={form.max_billing_cycles ?? ""}
            onChange={e => update({ max_billing_cycles: e.target.value ? +e.target.value : undefined })}
            min={1}
            placeholder="Unlimited"
          />
        </div>
      </fieldset>

      <button type="submit" disabled={submitting}
        style={{ background: "#6366f1", color: "#fff", padding: "10px 20px", border: "none", borderRadius: 6 }}>
        {submitting ? "Creating..." : "Create Plan"}
      </button>
    </form>
  );
}
```

### 3. Subscription Detail with Trial Management

```tsx
import { useState, useEffect } from "react";
import { subscriptionService } from "../services/api";

export function SubscriptionDetail({ subscriptionId }: { subscriptionId: string }) {
  const [sub, setSub] = useState<SubscriptionResponse | null>(null);
  const [payments, setPayments] = useState<SubscriptionPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState("");

  const load = async () => {
    const [subRes, payRes] = await Promise.all([
      subscriptionService.get(subscriptionId),
      subscriptionService.listPayments(subscriptionId),
    ]);
    setSub(subRes.data);
    setPayments(payRes.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, [subscriptionId]);

  const doAction = async (action: string, fn: () => Promise<any>) => {
    setActionLoading(action);
    try {
      await fn();
      await load(); // Refresh
    } catch (err: any) {
      alert(err.response?.data?.detail || `${action} failed`);
    } finally {
      setActionLoading("");
    }
  };

  if (loading || !sub) return <div>Loading...</div>;

  return (
    <div style={{ maxWidth: 700, padding: 20 }}>
      <h2>{sub.plan_name}</h2>
      <p><strong>Customer:</strong> {sub.customer_email}</p>
      <p>
        <strong>Status: </strong>
        <StatusBadge status={sub.status} />
      </p>

      {/* Trial banner */}
      {sub.is_in_trial && (
        <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", padding: 12, borderRadius: 6, marginBottom: 16 }}>
          <strong>🎁 Trial Active</strong>
          <p>
            {sub.trial_type === "free" ? "Free trial" : `Reduced price trial ($${sub.next_payment_amount})`}
            {" — "}
            {sub.trial_days_remaining} day{sub.trial_days_remaining !== 1 ? "s" : ""} remaining
          </p>
          <p style={{ fontSize: 13, color: "#6b7280" }}>
            Trial ends: {new Date(sub.trial_end!).toLocaleDateString()}
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              onClick={() => {
                const days = prompt("Extend by how many days?", "7");
                if (days) doAction("extend", () => subscriptionService.extendTrial(subscriptionId, +days));
              }}
              disabled={!!actionLoading}
              style={{ background: "#3b82f6", color: "#fff", padding: "6px 12px", border: "none", borderRadius: 4 }}
            >
              Extend Trial
            </button>
            <button
              onClick={() => doAction("end-trial", () => subscriptionService.endTrial(subscriptionId))}
              disabled={!!actionLoading}
              style={{ background: "#f59e0b", color: "#fff", padding: "6px 12px", border: "none", borderRadius: 4 }}
            >
              Convert to Paid Now
            </button>
          </div>
        </div>
      )}

      {/* Payment method */}
      <div style={{ border: "1px solid #e0e0e0", padding: 12, borderRadius: 6, marginBottom: 16 }}>
        <strong>Payment Method</strong>
        {sub.has_payment_method ? (
          <div>
            <p>Wallet: <code>{sub.customer_wallet_address}</code></p>
            <p>Chain: {sub.customer_chain} · Token: {sub.customer_token}</p>
          </div>
        ) : (
          <p style={{ color: "#f59e0b" }}>No payment method set — customer must pay manually each cycle.</p>
        )}
        <button
          onClick={() => {
            const wallet = prompt("Customer wallet address:");
            const chain = prompt("Chain (stellar/polygon/ethereum/base/tron/solana):");
            const token = prompt("Token (USDC/USDT/PYUSD):");
            if (wallet && chain && token) {
              doAction("payment-method", () =>
                subscriptionService.updatePaymentMethod(subscriptionId, {
                  wallet_address: wallet, chain, token
                })
              );
            }
          }}
          disabled={!!actionLoading}
          style={{ marginTop: 8, padding: "4px 10px" }}
        >
          {sub.has_payment_method ? "Update" : "Set"} Payment Method
        </button>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
        <StatCard label="Payments" value={sub.total_payments_collected} />
        <StatCard label="Revenue" value={`$${(sub.total_revenue ?? 0).toFixed(2)}`} />
        <StatCard label="Next Payment" value={
          sub.next_payment_at
            ? new Date(sub.next_payment_at).toLocaleDateString()
            : "—"
        } />
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {sub.status === "active" && (
          <>
            <button onClick={() => doAction("pause", () => subscriptionService.pause(subscriptionId))}
              disabled={!!actionLoading} style={{ padding: "6px 12px" }}>
              Pause
            </button>
            <button onClick={() => doAction("collect", () => subscriptionService.collectPayment(subscriptionId))}
              disabled={!!actionLoading} style={{ padding: "6px 12px", background: "#10b981", color: "#fff", border: "none", borderRadius: 4 }}>
              Collect Payment
            </button>
          </>
        )}
        {sub.status === "paused" && (
          <button onClick={() => doAction("resume", () => subscriptionService.resume(subscriptionId))}
            disabled={!!actionLoading} style={{ padding: "6px 12px" }}>
            Resume
          </button>
        )}
        {sub.status !== "cancelled" && (
          <button onClick={() => doAction("cancel", () => subscriptionService.cancel(subscriptionId))}
            disabled={!!actionLoading} style={{ padding: "6px 12px", color: "red" }}>
            Cancel
          </button>
        )}
      </div>

      {/* Payment history */}
      <h3>Payment History</h3>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #e0e0e0" }}>
            <th>Period</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Paid At</th>
          </tr>
        </thead>
        <tbody>
          {payments.map(p => (
            <tr key={p.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td>{new Date(p.period_start).toLocaleDateString()} — {new Date(p.period_end).toLocaleDateString()}</td>
              <td>${p.amount.toFixed(2)} {p.fiat_currency}</td>
              <td><StatusBadge status={p.status} /></td>
              <td>{p.paid_at ? new Date(p.paid_at).toLocaleDateString() : "—"}</td>
            </tr>
          ))}
          {payments.length === 0 && (
            <tr><td colSpan={4} style={{ textAlign: "center", padding: 20, color: "#999" }}>No payments yet</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    active: { bg: "#dcfce7", text: "#166534" },
    trialing: { bg: "#dbeafe", text: "#1e40af" },
    paused: { bg: "#fef3c7", text: "#92400e" },
    past_due: { bg: "#fee2e2", text: "#991b1b" },
    cancelled: { bg: "#f3f4f6", text: "#374151" },
    paid: { bg: "#dcfce7", text: "#166534" },
    pending: { bg: "#fef3c7", text: "#92400e" },
    created: { bg: "#e0e7ff", text: "#3730a3" },
    queued: { bg: "#fef3c7", text: "#92400e" },
    insufficient_funds: { bg: "#fee2e2", text: "#991b1b" },
    completed: { bg: "#dcfce7", text: "#166534" },
    failed: { bg: "#fee2e2", text: "#991b1b" },
    expired: { bg: "#f3f4f6", text: "#374151" },
  };
  const c = colors[status] || { bg: "#f3f4f6", text: "#374151" };
  return (
    <span style={{
      background: c.bg, color: c.text,
      padding: "2px 8px", borderRadius: 12, fontSize: 13, fontWeight: 600
    }}>
      {status.replace("_", " ")}
    </span>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ background: "#f9fafb", padding: 12, borderRadius: 6, textAlign: "center" }}>
      <div style={{ fontSize: 13, color: "#6b7280" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
```

### 4. Refund List with Status Handling

```tsx
import { useState, useEffect } from "react";
import { refundService } from "../services/api";

export function RefundList() {
  const [refunds, setRefunds] = useState<RefundResponse[]>([]);
  const [filter, setFilter] = useState("");

  const load = () => {
    refundService.list({ status: filter || undefined })
      .then(res => setRefunds(res.data));
  };

  useEffect(() => { load(); }, [filter]);

  const handleRetry = async (id: string) => {
    try {
      await refundService.retry(id);
      load();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Retry failed");
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm("Cancel this refund?")) return;
    try {
      await refundService.cancel(id);
      load();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Cancel failed");
    }
  };

  return (
    <div>
      <h2>Refunds</h2>

      {/* Filter */}
      <select value={filter} onChange={e => setFilter(e.target.value)} style={{ marginBottom: 12, padding: 6 }}>
        <option value="">All</option>
        <option value="pending">Pending</option>
        <option value="queued">Queued</option>
        <option value="insufficient_funds">Insufficient Funds</option>
        <option value="processing">Processing</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
      </select>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #e0e0e0" }}>
            <th>ID</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Source</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {refunds.map(r => (
            <tr key={r.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td style={{ fontFamily: "monospace", fontSize: 13 }}>{r.id}</td>
              <td>{r.amount} {r.token}</td>
              <td><StatusBadge status={r.status} /></td>
              <td>{r.refund_source === "external_wallet" ? "External" : "Platform"}</td>
              <td>{new Date(r.created_at).toLocaleDateString()}</td>
              <td>
                {(r.status === "failed" || r.status === "insufficient_funds") && (
                  <button onClick={() => handleRetry(r.id)} style={{ marginRight: 4 }}>Retry</button>
                )}
                {(r.status === "pending" || r.status === "queued") && (
                  <button onClick={() => handleCancel(r.id)} style={{ color: "red" }}>Cancel</button>
                )}
                {r.status === "queued" && r.queued_until && (
                  <span style={{ fontSize: 12, color: "#6b7280", marginLeft: 8 }}>
                    expires {new Date(r.queued_until).toLocaleDateString()}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

## Webhook Events

New events your frontend/backend should handle:

| Event | Description |
|-------|-------------|
| `subscription.created` | New subscription created via subscribe link |
| `subscription.trial_ending` | Trial ending in 3 days — show banner or send email |
| `subscription.trial_converted` | Trial converted to paid subscription |
| `subscription.payment_failed` | Payment attempt failed — notify customer |
| `subscription.cancelled` | Subscription cancelled (payment exhausted or manual) |
| `subscription.renewed` | Successful billing cycle — period advanced |
| `refund.created` | New refund (may be `queued` or `insufficient_funds`) |
| `refund.completed` | Refund processed successfully |
| `refund.failed` | Refund processing failed |

---

## Migration Checklist

### Types & Interfaces
- [ ] Add `RefundEligibility` type
- [ ] Update `RefundCreate` with `force`, `queue_if_insufficient`
- [ ] Update `RefundResponse` with `refund_source`, `settlement_status`, `merchant_balance_at_request`, `failure_reason`, `queued_until`
- [ ] Add `"queued"` and `"insufficient_funds"` to refund status union
- [ ] Update `SubscriptionPlanCreate` with `trial_type`, `trial_price`, `setup_fee`, `max_billing_cycles`
- [ ] Update `SubscriptionPlanResponse` with same new fields
- [ ] Update `SubscriptionCreate` with `customer_wallet_address`, `customer_chain`, `customer_token`, `custom_trial_days`
- [ ] Update `SubscriptionResponse` with `is_in_trial`, `trial_days_remaining`, `trial_type`, `total_payments_collected`, `total_revenue`, `next_payment_amount`, `has_payment_method`, customer fields

### API Calls
- [ ] Add `GET /refunds/eligibility/{id}` call
- [ ] Update `POST /refunds` to send `force` / `queue_if_insufficient`
- [ ] Add `POST /refunds/process-queued` call (admin page)
- [ ] Add `POST /subscriptions/{id}/extend-trial`
- [ ] Add `POST /subscriptions/{id}/end-trial`
- [ ] Add `PUT /subscriptions/{id}/payment-method`
- [ ] Add `POST /subscriptions/{id}/collect-payment`
- [ ] Add `POST /subscriptions/{id}/renew`

### UI Components
- [ ] Refund form: add eligibility pre-check, queue/force buttons
- [ ] Refund list: handle `queued`, `insufficient_funds` statuses, add retry/cancel
- [ ] Plan creation form: add trial type, trial price, setup fee, max cycles
- [ ] Subscription detail: add trial banner with extend/end-trial actions
- [ ] Subscription detail: add payment method section
- [ ] Subscription detail: show payment stats (total collected, revenue)
- [ ] Subscription list: show trial badge for trialing subscriptions
- [ ] Plan detail/list: show subscribe link with copy button

---

## Copy Subscribe Link — Frontend Implementation

Every `SubscriptionPlanResponse` now includes a `subscribe_url` field. This is the public URL customers visit to subscribe to the plan (like the checkout URL on payment links). Display this alongside each plan and let merchants copy it with one click.

### React Example — Copy Link Button

```tsx
import { useState } from "react";

interface CopySubscribeLinkProps {
  subscribeUrl: string | null;
}

export function CopySubscribeLink({ subscribeUrl }: CopySubscribeLinkProps) {
  const [copied, setCopied] = useState(false);

  if (!subscribeUrl) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(subscribeUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers / insecure contexts
      const textarea = document.createElement("textarea");
      textarea.value = subscribeUrl;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        readOnly
        value={subscribeUrl}
        className="flex-1 px-3 py-2 border rounded-lg bg-gray-50 text-sm text-gray-700"
      />
      <button
        onClick={handleCopy}
        className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm"
      >
        {copied ? "Copied!" : "Copy Link"}
      </button>
    </div>
  );
}
```

### Usage in Plan List / Detail Page

```tsx
{plans.map((plan) => (
  <div key={plan.id} className="p-4 border rounded-lg">
    <h3>{plan.name}</h3>
    <p>{plan.amount} {plan.currency} / {plan.interval}</p>
    <CopySubscribeLink subscribeUrl={plan.subscribe_url} />
  </div>
))}
```

To change the copy method (e.g. to use a toast notification, a different clipboard library, or a share dialog instead), replace the `handleCopy` function body. For example, to use the Web Share API on mobile:

```tsx
const handleCopy = async () => {
  if (navigator.share) {
    await navigator.share({
      title: "Subscribe to " + planName,
      url: subscribeUrl,
    });
  } else {
    await navigator.clipboard.writeText(subscribeUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
};
```

Or to use a toast library like `react-hot-toast`:

```tsx
import toast from "react-hot-toast";

const handleCopy = async () => {
  await navigator.clipboard.writeText(subscribeUrl);
  toast.success("Subscribe link copied!");
};
```

### Webhook Handlers
- [ ] Handle `subscription.trial_ending` — show in-app notification or email
- [ ] Handle `subscription.payment_failed` — show alert to merchant
- [ ] Handle `subscription.cancelled` — update UI state
