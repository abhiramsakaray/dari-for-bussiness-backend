/**
 * ChainPe Payment Button SDK
 * Version: 1.0.0
 * 
 * Easy integration for merchants to add "Pay with ChainPe" button
 */

(function(window) {
    'use strict';
    
    const ChainPe = {
        config: {
            apiUrl: 'https://chainpe.onrender.com',  // Production URL
            buttonId: 'chainpe-payment-button',
            modalId: 'chainpe-modal'
        },
        
        /**
         * Initialize ChainPe payment button
         * @param {Object} options - Configuration options
         * @param {string} options.apiKey - Your ChainPe API key
         * @param {number} options.amount - Payment amount in USDC
         * @param {string} options.orderId - Your order/transaction ID
         * @param {string} options.successUrl - URL to redirect after successful payment
         * @param {string} options.cancelUrl - URL to redirect if payment is cancelled
         * @param {Object} options.metadata - Optional metadata (customer info, etc.)
         */
        init: function(options) {
            if (!options.apiKey) {
                console.error('ChainPe: API key is required');
                return;
            }
            
            this.options = options;
            this.renderButton();
            this.attachEventListeners();
        },
        
        /**
         * Render the ChainPe payment button
         */
        renderButton: function() {
            const button = document.getElementById(this.config.buttonId);
            if (!button) {
                console.error(`ChainPe: Button element with id "${this.config.buttonId}" not found`);
                return;
            }
            
            // Style the button
            button.style.cssText = `
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: 600;
                border-radius: 8px;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            `;
            
            // Add hover effect
            button.onmouseover = function() {
                this.style.transform = 'translateY(-2px)';
                this.style.boxShadow = '0 6px 12px rgba(0, 0, 0, 0.15)';
            };
            
            button.onmouseout = function() {
                this.style.transform = 'translateY(0)';
                this.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
            };
            
            // Add icon and text
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="white"/>
                    <path d="M2 17L12 22L22 17" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M2 12L12 17L22 12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                Pay with ChainPe
            `;
        },
        
        /**
         * Attach click event listener
         */
        attachEventListeners: function() {
            const button = document.getElementById(this.config.buttonId);
            if (button) {
                button.addEventListener('click', () => this.initiatePayment());
            }
        },
        
        /**
         * Create payment session and redirect to checkout
         */
        initiatePayment: async function() {
            const button = document.getElementById(this.config.buttonId);
            
            try {
                // Disable button and show loading
                button.disabled = true;
                button.innerHTML = `
                    <svg class="spinner" width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="12" cy="12" r="10" stroke="white" stroke-width="2" fill="none" opacity="0.25"/>
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="white" stroke-width="2" fill="none" stroke-linecap="round"/>
                    </svg>
                    Processing...
                `;
                
                // Add spinner animation
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes spin {
                        to { transform: rotate(360deg); }
                    }
                    .spinner { animation: spin 1s linear infinite; }
                `;
                document.head.appendChild(style);
                
                // Create payment session
                const response = await fetch(`${this.config.apiUrl}/api/sessions/create`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': this.options.apiKey
                    },
                    body: JSON.stringify({
                        amount_usdc: this.options.amount,
                        order_id: this.options.orderId,
                        success_url: this.options.successUrl,
                        cancel_url: this.options.cancelUrl,
                        metadata: this.options.metadata || {}
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to create payment session');
                }
                
                const data = await response.json();
                
                // Redirect to ChainPe checkout page
                window.location.href = data.checkout_url;
                
            } catch (error) {
                console.error('ChainPe payment error:', error);
                alert(`Payment error: ${error.message}`);
                
                // Re-enable button
                button.disabled = false;
                this.renderButton();
            }
        },
        
        /**
         * Verify payment status (call this on success_url page)
         * @param {string} sessionId - Payment session ID from URL parameter
         * @returns {Promise<Object>} Payment session data
         */
        verifyPayment: async function(sessionId) {
            try {
                const response = await fetch(`${this.config.apiUrl}/api/sessions/${sessionId}`, {
                    method: 'GET',
                    headers: {
                        'X-API-Key': this.options.apiKey
                    }
                });
                
                if (!response.ok) {
                    throw new Error('Failed to verify payment');
                }
                
                return await response.json();
                
            } catch (error) {
                console.error('ChainPe verification error:', error);
                throw error;
            }
        }
    };
    
    // Expose to window
    window.ChainPe = ChainPe;
    
})(window);
