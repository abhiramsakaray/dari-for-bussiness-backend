// src/components/Settings.tsx
import React, { useState } from 'react';
import { authService } from '../services/auth';

export const Settings = () => {
  const [showApiKey, setShowApiKey] = useState(false);
  const apiKey = authService.getApiKey();

  const copyToClipboard = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey);
      alert('API key copied to clipboard!');
    }
  };

  return (
    <div className="settings-page">
      <h1>Settings</h1>
      
      <div className="api-key-section">
        <h2>API Key</h2>
        <p>Use this key to integrate ChainPe payments into your website.</p>
        
        <div className="api-key-display">
          <code>
            {showApiKey ? apiKey : '••••••••••••••••••••••••'}
          </code>
          
          <button onClick={() => setShowApiKey(!showApiKey)}>
            {showApiKey ? '👁️ Hide' : '👁️ Show'}
          </button>
          
          <button onClick={copyToClipboard}>
            📋 Copy
          </button>
        </div>
        
        <div className="usage-example">
          <h3>Quick Integration</h3>
          <pre>{`
<!-- Add to your website -->
<script src="https://your-domain.com/chainpe-button.js"></script>
<button id="chainpe-payment-button"></button>

<script>
  ChainPe.init({
    apiKey: '${apiKey || 'your_api_key'}',
    amount: 50.00,
    orderId: 'ORDER-123'
  });
</script>
          `}</pre>
        </div>
      </div>
    </div>
  );
};
