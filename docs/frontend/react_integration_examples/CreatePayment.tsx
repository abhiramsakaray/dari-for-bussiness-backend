// src/pages/CreatePayment.tsx - Multi-Chain Version
import React, { useState } from 'react';
import { chainpeService } from '../services/chainpe';

// Available payment options
const TOKENS = ['USDC', 'USDT', 'PYUSD'];
const CHAINS = [
  { value: 'stellar', label: 'Stellar' },
  { value: 'polygon', label: 'Polygon' },
  { value: 'ethereum', label: 'Ethereum' },
  { value: 'base', label: 'Base' },
  { value: 'tron', label: 'Tron' },
];

export const CreatePayment = () => {
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [orderId, setOrderId] = useState('');
  const [selectedTokens, setSelectedTokens] = useState<string[]>(['USDC']);
  const [selectedChains, setSelectedChains] = useState<string[]>(['stellar', 'polygon']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [session, setSession] = useState<any>(null);

  const toggleToken = (token: string) => {
    setSelectedTokens(prev => 
      prev.includes(token) 
        ? prev.filter(t => t !== token)
        : [...prev, token]
    );
  };

  const toggleChain = (chain: string) => {
    setSelectedChains(prev => 
      prev.includes(chain) 
        ? prev.filter(c => c !== chain)
        : [...prev, chain]
    );
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Create multi-chain payment session
      const response = await chainpeService.createSession({
        amount_fiat: parseFloat(amount),
        fiat_currency: currency,
        accepted_tokens: selectedTokens,
        accepted_chains: selectedChains,
        order_id: orderId || `ORDER-${Date.now()}`,
        success_url: window.location.origin + '/dashboard/success',
        cancel_url: window.location.origin + '/dashboard',
        metadata: {
          created_from: 'dashboard',
          timestamp: new Date().toISOString()
        }
      });

      setSession(response);
      console.log('Payment session created:', response);
      
      // Optionally redirect to checkout
      // window.location.href = response.checkout_url;
    } catch (err: any) {
      console.error('Payment creation failed:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to create payment';
      setError(errorMsg);
      
      // Log the full error for debugging
      console.error('Full error:', {
        status: err.response?.status,
        data: err.response?.data,
        message: err.message
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="create-payment">
      <h1>Create Payment Session</h1>
      <p className="subtitle">Accept stablecoins across multiple blockchains</p>

      <form onSubmit={handleCreate}>
        <div className="form-group">
          <label>Amount</label>
          <div className="amount-input">
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="100.00"
              required
            />
            <select 
              value={currency} 
              onChange={(e) => setCurrency(e.target.value)}
              className="currency-select"
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label>Accepted Tokens</label>
          <div className="checkbox-group">
            {TOKENS.map(token => (
              <label key={token} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTokens.includes(token)}
                  onChange={() => toggleToken(token)}
                />
                <span>{token}</span>
              </label>
            ))}
          </div>
          <small>Select which stablecoins to accept</small>
        </div>

        <div className="form-group">
          <label>Accepted Chains</label>
          <div className="checkbox-group">
            {CHAINS.map(chain => (
              <label key={chain.value} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedChains.includes(chain.value)}
                  onChange={() => toggleChain(chain.value)}
                />
                <span>{chain.label}</span>
              </label>
            ))}
          </div>
          <small>Select which blockchain networks to support</small>
        </div>

        <div className="form-group">
          <label>Order ID (optional)</label>
          <input
            type="text"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
            placeholder="ORDER-123"
          />
          <small>Leave empty to auto-generate</small>
        </div>

        {error && (
          <div className="error-message">
            ❌ {error}
          </div>
        )}

        <button 
          type="submit" 
          disabled={loading || selectedTokens.length === 0 || selectedChains.length === 0}
          className="submit-button"
        >
          {loading ? '⏳ Creating...' : '🚀 Create Payment Session'}
        </button>
      </form>

      {session && (
        <div className="session-details">
          <h2>✅ Payment Session Created!</h2>
          
          <div className="detail-grid">
            <div className="detail-row">
              <strong>Session ID:</strong>
              <code>{session.session_id}</code>
            </div>
            <div className="detail-row">
              <strong>Amount:</strong>
              <span>{session.amount_fiat} {session.fiat_currency}</span>
            </div>
            <div className="detail-row">
              <strong>Order ID:</strong>
              <span>{session.order_id}</span>
            </div>
            <div className="detail-row">
              <strong>Status:</strong>
              <span className={`status ${session.status}`}>{session.status}</span>
            </div>
            <div className="detail-row">
              <strong>Accepted Tokens:</strong>
              <span>{session.accepted_tokens?.join(', ') || 'USDC'}</span>
            </div>
            <div className="detail-row">
              <strong>Accepted Chains:</strong>
              <span>{session.accepted_chains?.join(', ') || 'stellar'}</span>
            </div>
            <div className="detail-row">
              <strong>Expires At:</strong>
              <span>{new Date(session.expires_at).toLocaleString()}</span>
            </div>
          </div>

          <div className="actions">
            <a 
              href={session.checkout_url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="button primary"
            >
              💳 Open Checkout Page →
            </a>
            <button 
              onClick={() => navigator.clipboard.writeText(session.checkout_url)}
              className="button secondary"
            >
              📋 Copy Checkout URL
            </button>
            <button 
              onClick={() => setSession(null)}
              className="button tertiary"
            >
              ← Create Another
            </button>
          </div>

          <div className="checkout-preview">
            <p><strong>Checkout URL:</strong></p>
            <code className="url-display">{session.checkout_url}</code>
          </div>
        </div>
      )}

      <style jsx>{`
        .create-payment {
          max-width: 600px;
          margin: 0 auto;
          padding: 24px;
        }

        .subtitle {
          color: #6c757d;
          margin-bottom: 24px;
        }

        .form-group {
          margin-bottom: 20px;
        }

        .form-group label {
          display: block;
          font-weight: 600;
          margin-bottom: 8px;
          color: #1a1a2e;
        }

        .amount-input {
          display: flex;
          gap: 8px;
        }

        .amount-input input {
          flex: 1;
        }

        .currency-select {
          width: 100px;
        }

        input[type="text"],
        input[type="number"],
        select {
          width: 100%;
          padding: 10px;
          border: 2px solid #e9ecef;
          border-radius: 8px;
          font-size: 14px;
        }

        .checkbox-group {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-bottom: 6px;
        }

        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 12px;
          border: 2px solid #e9ecef;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .checkbox-label:hover {
          border-color: #667eea;
          background: #f8f9ff;
        }

        .checkbox-label input:checked + span {
          font-weight: 600;
          color: #667eea;
        }

        small {
          color: #6c757d;
          font-size: 12px;
        }

        .submit-button {
          width: 100%;
          padding: 14px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 12px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.2s;
        }

        .submit-button:hover:not(:disabled) {
          opacity: 0.9;
        }

        .submit-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .error-message {
          padding: 12px;
          background: #f8d7da;
          color: #721c24;
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .session-details {
          margin-top: 32px;
          padding: 24px;
          background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
          border-radius: 16px;
        }

        .session-details h2 {
          margin-bottom: 20px;
          color: #28a745;
        }

        .detail-grid {
          margin-bottom: 24px;
        }

        .detail-row {
          display: flex;
          justify-content: space-between;
          padding: 12px 0;
          border-bottom: 1px solid #dee2e6;
        }

        .detail-row:last-child {
          border-bottom: none;
        }

        .status {
          padding: 4px 12px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
        }

        .status.created {
          background: #fff3cd;
          color: #856404;
        }

        .actions {
          display: flex;
          gap: 12px;
          margin-bottom: 20px;
        }

        .button {
          flex: 1;
          padding: 12px;
          border-radius: 8px;
          text-align: center;
          text-decoration: none;
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.2s;
          border: none;
        }

        .button:hover {
          opacity: 0.9;
        }

        .button.primary {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        }

        .button.secondary {
          background: white;
          border: 2px solid #667eea;
          color: #667eea;
        }

        .button.tertiary {
          background: #e9ecef;
          color: #495057;
        }

        .checkout-preview {
          padding: 16px;
          background: white;
          border-radius: 8px;
        }

        .url-display {
          display: block;
          padding: 12px;
          background: #f8f9fa;
          border-radius: 6px;
          font-size: 12px;
          word-break: break-all;
          margin-top: 8px;
        }
      `}</style>
    </div>
  );
};
