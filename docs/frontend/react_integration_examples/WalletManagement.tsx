// src/pages/WalletManagement.tsx - Merchant Wallet Management (Multi-Chain)
import React, { useState, useEffect } from 'react';
import { chainpeService, MerchantWallet } from '../services/chainpe';

const AVAILABLE_CHAINS = [
  { value: 'stellar', label: 'Stellar', icon: '⭐', example: 'GXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' },
  { value: 'polygon', label: 'Polygon', icon: '💜', example: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb' },
  { value: 'ethereum', label: 'Ethereum', icon: '💎', example: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb' },
  { value: 'base', label: 'Base', icon: '🔵', example: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb' },
  { value: 'tron', label: 'Tron', icon: '🔴', example: 'TRX7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t' },
];

export const WalletManagement = () => {
  const [wallets, setWallets] = useState<MerchantWallet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editMode, setEditMode] = useState<string | null>(null);
  const [newAddress, setNewAddress] = useState('');

  useEffect(() => {
    loadWallets();
  }, []);

  const loadWallets = async () => {
    try {
      setLoading(true);
      const data = await chainpeService.listWallets();
      setWallets(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load wallets');
    } finally {
      setLoading(false);
    }
  };

  const handleAddWallet = async (chain: string) => {
    if (!newAddress.trim()) {
      setError('Please enter a wallet address');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      await chainpeService.addWallet(chain, newAddress.trim());
      
      setSuccess(`✅ Wallet added for ${chain}`);
      setEditMode(null);
      setNewAddress('');
      
      await loadWallets();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add wallet');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteWallet = async (chain: string) => {
    if (!confirm(`Remove ${chain} wallet?`)) return;

    try {
      setLoading(true);
      await chainpeService.deleteWallet(chain);
      setSuccess(`✅ Wallet removed for ${chain}`);
      await loadWallets();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete wallet');
    } finally {
      setLoading(false);
    }
  };

  const getWalletForChain = (chain: string) => 
    wallets.find(w => w.chain === chain && w.is_active);

  return (
    <div className="wallet-management">
      <h1>💼 Wallet Management</h1>
      <p>Configure wallet addresses for each blockchain</p>

      {error && <div className="alert error">⚠️ {error}</div>}
      {success && <div className="alert success">{success}</div>}

      <div className="wallets-grid">
        {AVAILABLE_CHAINS.map(chain => {
          const wallet = getWalletForChain(chain.value);
          const isEditing = editMode === chain.value;

          return (
            <div key={chain.value} className={`wallet-card ${wallet ? 'active' : ''}`}>
              <div className="card-header">
                <span className="icon">{chain.icon}</span>
                <h3>{chain.label}</h3>
                {wallet && !isEditing && (
                  <button onClick={() => setEditMode(chain.value)}>✏️</button>
                )}
              </div>

              {!isEditing && wallet && (
                <div>
                  <code>{wallet.wallet_address}</code>
                  <button onClick={() => handleDeleteWallet(chain.value)}>Remove</button>
                </div>
              )}

              {!isEditing && !wallet && (
                <button onClick={() => setEditMode(chain.value)}>+ Add Wallet</button>
              )}

              {isEditing && (
                <div>
                  <input
                    value={newAddress}
                    onChange={(e) => setNewAddress(e.target.value)}
                    placeholder={chain.example}
                  />
                  <button onClick={() => handleAddWallet(chain.value)}>Save</button>
                  <button onClick={() => setEditMode(null)}>Cancel</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
