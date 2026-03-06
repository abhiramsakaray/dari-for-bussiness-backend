// src/pages/PaymentFlow.tsx - Complete Customer Payment Flow Example
import React, { useState, useEffect } from 'react';
import { chainpeService, PaymentOption } from '../services/chainpe';

interface PaymentFlowProps {
  sessionId: string;
}

export const PaymentFlow: React.FC<PaymentFlowProps> = ({ sessionId }) => {
  const [session, setSession] = useState<any>(null);
  const [paymentOptions, setPaymentOptions] = useState<PaymentOption[]>([]);
  const [selectedOption, setSelectedOption] = useState<PaymentOption | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState<string | null>(null);

  // Load session and payment options
  useEffect(() => {
    loadSessionData();
  }, [sessionId]);

  // Poll for payment status
  useEffect(() => {
    if (!session || session.status !== 'created') return;

    const stopPolling = chainpeService.pollSessionStatus(
      sessionId,
      (status) => {
        console.log('Payment status changed:', status);
        if (status === 'paid') {
          // Redirect to success page
          window.location.href = session.success_url;
        } else if (status === 'expired') {
          setError('Payment session expired');
        }
      }
    );

    return stopPolling;
  }, [session]);

  const loadSessionData = async () => {
    try {
      setLoading(true);
      
      // Get session details
      const sessionData = await chainpeService.getSession(sessionId);
      setSession(sessionData);

      // Get payment options
      const options = await chainpeService.getPaymentOptions(sessionId);
      setPaymentOptions(options);

      // If already selected, set the option
      if (sessionData.token && sessionData.chain) {
        const selected = options.find(
          opt => opt.token === sessionData.token && opt.chain === sessionData.chain
        );
        setSelectedOption(selected || null);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load payment data');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectOption = async (option: PaymentOption) => {
    try {
      setLoading(true);
      
      // Call API to select payment method
      await chainpeService.selectPaymentMethod(sessionId, {
        token: option.token,
        chain: option.chain
      });

      // Update selected option
      setSelectedOption(option);
      
      // Reload session to get updated wallet address
      await loadSessionData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to select payment method');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  const getChainIcon = (chain: string) => {
    const icons: Record<string, string> = {
      stellar: '⭐',
      polygon: '💜',
      ethereum: '💎',
      base: '🔵',
      tron: '🔴',
    };
    return icons[chain] || '🔗';
  };

  if (loading && !session) {
    return (
      <div className="payment-flow loading">
        <div className="spinner" />
        <p>Loading payment details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="payment-flow error">
        <h2>⚠️ Error</h2>
        <p>{error}</p>
        <button onClick={() => window.location.href = session?.cancel_url}>
          Return to Store
        </button>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  return (
    <div className="payment-flow">
      {/* Payment Amount */}
      <div className="payment-header">
        <h1>Complete Payment</h1>
        <div className="amount">
          <span className="currency">{session.fiat_currency}</span>
          <span className="value">{session.amount_fiat.toFixed(2)}</span>
        </div>
        {session.order_id && (
          <div className="order-id">Order: {session.order_id}</div>
        )}
      </div>

      {/* Payment Method Selection */}
      {!selectedOption && (
        <div className="payment-options">
          <h2>Choose Payment Method</h2>
          <div className="options-grid">
            {paymentOptions.map((option, index) => (
              <button
                key={index}
                className="payment-option"
                onClick={() => handleSelectOption(option)}
                disabled={loading}
              >
                <div className="option-header">
                  <span className="chain-icon">{getChainIcon(option.chain)}</span>
                  <div className="option-info">
                    <div className="token-name">{option.token}</div>
                    <div className="chain-name">{option.chain_display}</div>
                  </div>
                </div>
                <div className="option-amount">
                  {option.amount.toFixed(2)} {option.token}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Payment Details */}
      {selectedOption && (
        <div className="payment-details">
          <div className="selected-method">
            <h3>
              {getChainIcon(selectedOption.chain)} 
              {selectedOption.token} on {selectedOption.chain_display}
            </h3>
            <button 
              onClick={() => setSelectedOption(null)}
              className="change-button"
            >
              Change Method
            </button>
          </div>

          {/* QR Code */}
          <div className="qr-section">
            <img 
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(selectedOption.wallet_address)}`}
              alt="Payment QR Code"
              className="qr-code"
            />
          </div>

          {/* Payment Instructions */}
          <div className="instructions">
            <div className="instruction-row">
              <label>Send To</label>
              <div className="value-copy">
                <code>{selectedOption.wallet_address}</code>
                <button 
                  onClick={() => copyToClipboard(selectedOption.wallet_address, 'address')}
                  className="copy-btn"
                >
                  {copied === 'address' ? '✓' : '📋'}
                </button>
              </div>
            </div>

            <div className="instruction-row">
              <label>Amount</label>
              <div className="value-copy">
                <code>{selectedOption.amount} {selectedOption.token}</code>
                <button 
                  onClick={() => copyToClipboard(selectedOption.amount.toString(), 'amount')}
                  className="copy-btn"
                >
                  {copied === 'amount' ? '✓' : '📋'}
                </button>
              </div>
            </div>

            {selectedOption.memo && (
              <div className="instruction-row">
                <label>Memo (Required for Stellar)</label>
                <div className="value-copy">
                  <code>{selectedOption.memo}</code>
                  <button 
                    onClick={() => copyToClipboard(selectedOption.memo!, 'memo')}
                    className="copy-btn"
                  >
                    {copied === 'memo' ? '✓' : '📋'}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Status */}
          <div className="payment-status">
            <div className="status-indicator">
              <div className="spinner-small" />
              <span>Waiting for payment...</span>
            </div>
            <p className="status-note">
              Your payment will be confirmed within seconds
            </p>
          </div>
        </div>
      )}

      {/* Timer */}
      <div className="timer">
        Expires in: {calculateTimeRemaining(session.expires_at)}
      </div>

      <style jsx>{`
        .payment-flow {
          max-width: 500px;
          margin: 0 auto;
          padding: 24px;
        }

        .payment-header {
          text-align: center;
          margin-bottom: 32px;
        }

        .amount {
          font-size: 48px;
          font-weight: 700;
          margin: 16px 0;
        }

        .currency {
          font-size: 24px;
          color: #6c757d;
          margin-right: 8px;
        }

        .order-id {
          color: #6c757d;
          font-size: 14px;
        }

        .payment-options {
          margin-bottom: 32px;
        }

        .payment-options h2 {
          margin-bottom: 16px;
        }

        .options-grid {
          display: grid;
          gap: 12px;
        }

        .payment-option {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px;
          border: 2px solid #e9ecef;
          border-radius: 12px;
          background: white;
          cursor: pointer;
          transition: all 0.2s;
        }

        .payment-option:hover:not(:disabled) {
          border-color: #667eea;
          background: #f8f9ff;
        }

        .payment-option:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .option-header {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .chain-icon {
          font-size: 24px;
        }

        .token-name {
          font-weight: 600;
          font-size: 16px;
        }

        .chain-name {
          font-size: 12px;
          color: #6c757d;
        }

        .option-amount {
          font-weight: 600;
          color: #1a1a2e;
        }

        .payment-details {
          background: #f8f9fa;
          padding: 24px;
          border-radius: 16px;
        }

        .selected-method {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }

        .change-button {
          padding: 6px 12px;
          background: white;
          border: 1px solid #dee2e6;
          border-radius: 6px;
          cursor: pointer;
        }

        .qr-section {
          text-align: center;
          margin-bottom: 24px;
        }

        .qr-code {
          padding: 16px;
          background: white;
          border-radius: 12px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }

        .instructions {
          margin-bottom: 24px;
        }

        .instruction-row {
          margin-bottom: 16px;
        }

        .instruction-row label {
          display: block;
          font-size: 12px;
          color: #6c757d;
          margin-bottom: 6px;
          text-transform: uppercase;
        }

        .value-copy {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .value-copy code {
          flex: 1;
          padding: 10px;
          background: white;
          border-radius: 6px;
          font-size: 13px;
          word-break: break-all;
        }

        .copy-btn {
          padding: 8px 12px;
          background: #667eea;
          color: white;
          border: none;
          border-radius: 6px;
          cursor: pointer;
          font-size: 14px;
        }

        .payment-status {
          text-align: center;
          padding: 20px;
          background: white;
          border-radius: 12px;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          font-weight: 600;
          margin-bottom: 8px;
        }

        .status-note {
          font-size: 12px;
          color: #6c757d;
        }

        .timer {
          text-align: center;
          margin-top: 24px;
          color: #6c757d;
        }

        .spinner, .spinner-small {
          border: 3px solid #e9ecef;
          border-top: 3px solid #667eea;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        .spinner {
          width: 40px;
          height: 40px;
          margin: 0 auto;
        }

        .spinner-small {
          width: 20px;
          height: 20px;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

// Helper function to calculate time remaining
function calculateTimeRemaining(expiresAt: string): string {
  const now = new Date().getTime();
  const expires = new Date(expiresAt).getTime();
  const diff = expires - now;

  if (diff <= 0) return 'Expired';

  const minutes = Math.floor(diff / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);

  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export default PaymentFlow;
