// src/services/chainpe.ts - Dari for Business Multi-Chain Payment Service
import api from './api';

// ============= TYPE DEFINITIONS =============

export interface PaymentSessionCreate {
  amount_fiat: number;
  fiat_currency?: string;  // USD, EUR, GBP
  accepted_tokens?: string[];  // ['USDC', 'USDT', 'PYUSD']
  accepted_chains?: string[];  // ['stellar', 'polygon', 'ethereum', 'base', 'tron']
  order_id?: string;
  success_url: string;
  cancel_url: string;
  metadata?: Record<string, any>;
  
  // Legacy support (for backward compatibility)
  amount_usdc?: number;
}

export interface PaymentSession {
  session_id: string;
  merchant_id: string;
  amount_fiat: number;
  fiat_currency: string;
  amount_usdc?: number;  // Legacy field
  token?: string;  // Selected token (after customer choice)
  chain?: string;  // Selected chain (after customer choice)
  accepted_tokens?: string[];
  accepted_chains?: string[];
  status: 'created' | 'paid' | 'expired' | 'cancelled';
  checkout_url: string;
  success_url: string;
  cancel_url: string;
  order_id?: string;
  tx_hash?: string;
  created_at: string;
  expires_at: string;
  paid_at?: string;
}

export interface PaymentOption {
  token: string;
  chain: string;
  chain_display: string;
  amount: number;
  wallet_address: string;
  memo?: string;
}

export interface SelectPaymentMethod {
  token: string;
  chain: string;
}

export interface MerchantWallet {
  id: string;
  chain: string;
  wallet_address: string;
  is_active: boolean;
  created_at: string;
}

// ============= PAYMENT SERVICES =============

class DariService {
  
  /**
   * Create a new payment session
   */
  async createSession(data: PaymentSessionCreate): Promise<PaymentSession> {
    const response = await api.post('/api/sessions', data);
    return response.data;
  }

  /**
   * Get payment session details
   */
  async getSession(sessionId: string): Promise<PaymentSession> {
    const response = await api.get(`/api/sessions/${sessionId}`);
    return response.data;
  }

  /**
   * Get payment session status (lightweight endpoint)
   */
  async getSessionStatus(sessionId: string): Promise<{ status: string }> {
    const response = await api.get(`/api/sessions/${sessionId}/status`);
    return response.data;
  }

  /**
   * Get available payment options for a session
   * Returns list of token/chain combinations with calculated amounts
   */
  async getPaymentOptions(sessionId: string): Promise<PaymentOption[]> {
    const response = await api.get(`/api/sessions/${sessionId}/options`);
    return response.data;
  }

  /**
   * Select payment method for a session
   * Must be called before customer sends payment
   */
  async selectPaymentMethod(
    sessionId: string, 
    method: SelectPaymentMethod
  ): Promise<PaymentSession> {
    const response = await api.post(`/api/sessions/${sessionId}/select`, method);
    return response.data;
  }

  // ============= MERCHANT WALLET MANAGEMENT =============

  /**
   * List all merchant wallets
   */
  async listWallets(): Promise<MerchantWallet[]> {
    const response = await api.get('/merchant/wallets');
    return response.data.wallets;
  }

  /**
   * Add or update wallet for a chain
   */
  async addWallet(chain: string, walletAddress: string): Promise<MerchantWallet> {
    const response = await api.post('/merchant/wallets', {
      chain,
      wallet_address: walletAddress
    });
    return response.data;
  }

  /**
   * Get wallet for specific chain
   */
  async getWallet(chain: string): Promise<MerchantWallet> {
    const response = await api.get(`/merchant/wallets/${chain}`);
    return response.data;
  }

  /**
   * Deactivate wallet for a chain
   */
  async deleteWallet(chain: string): Promise<void> {
    await api.delete(`/merchant/wallets/${chain}`);
  }

  // ============= PAYMENT POLLING =============

  /**
   * Poll for payment status updates
   * Useful for integrating with your order system
   */
  async pollSessionStatus(
    sessionId: string,
    onStatusChange: (status: string) => void,
    intervalMs: number = 3000
  ): () => void {
    let isPolling = true;
    let lastStatus = '';

    const poll = async () => {
      if (!isPolling) return;

      try {
        const { status } = await this.getSessionStatus(sessionId);
        
        if (status !== lastStatus) {
          lastStatus = status;
          onStatusChange(status);
        }

        // Stop polling if terminal state reached
        if (status === 'paid' || status === 'expired' || status === 'cancelled') {
          isPolling = false;
          return;
        }

        // Schedule next poll
        setTimeout(poll, intervalMs);
      } catch (error) {
        console.error('Polling error:', error);
        setTimeout(poll, intervalMs * 2); // Back off on error
      }
    };

    // Start polling
    poll();

    // Return cleanup function
    return () => {
      isPolling = false;
    };
  }
}

// Export singleton instance
export const dariService = new DariService();
export const chainpeService = dariService; // Legacy alias for backward compatibility
export default dariService;
