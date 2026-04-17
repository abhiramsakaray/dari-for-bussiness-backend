# Pre-Launch Checklist

Use this checklist to ensure everything is ready before going live.

---

## ✅ Phase 1: Development Setup

### Dependencies
- [ ] Python 3.11+ installed
- [ ] PostgreSQL 14+ installed and running
- [ ] Redis installed (optional, for caching)
- [ ] Node.js 18+ installed (for contract deployment)
- [ ] `pip install -r requirements.txt`
- [ ] `pip install stellar-sdk eth-account`
- [ ] `cd contracts && npm install`

### Environment Configuration
- [ ] `.env` file created from `.env.example`
- [ ] `DATABASE_URL` set to PostgreSQL connection string
- [ ] `JWT_SECRET` changed from default (32+ chars)
- [ ] `API_KEY_SECRET` changed from default
- [ ] `PII_ENCRYPTION_KEY` generated and set
- [ ] `ADMIN_EMAIL` set to your email
- [ ] `ADMIN_PASSWORD` changed from default
- [ ] `APP_BASE_URL` set to your domain
- [ ] `CORS_ORIGINS` set to specific domains (not `*`)
- [ ] `USE_MAINNET` set correctly (false for testing, true for production)

### Database
- [ ] Database created: `createdb dari_payments`
- [ ] Database initialized: `python init_db.py`
- [ ] Database connection tested
- [ ] Admin user created

---

## ✅ Phase 2: Blockchain Configuration

### Relayer Wallets
- [ ] `RELAYER_PRIVATE_KEY` generated and set (EVM chains)
- [ ] Relayer wallet funded with gas tokens:
  - [ ] ETH (Ethereum)
  - [ ] MATIC (Polygon)
  - [ ] ETH (Base)
  - [ ] BNB (BSC)
  - [ ] ETH (Arbitrum)
  - [ ] AVAX (Avalanche)
- [ ] `TRON_RELAYER_PRIVATE_KEY` set (if using Tron)
- [ ] `SOLANA_RELAYER_PRIVATE_KEY` set (if using Solana)
- [ ] `SOROBAN_RELAYER_SECRET_KEY` set (if using Soroban)

### RPC Endpoints (Production)
- [ ] `ETHEREUM_MAINNET_RPC_URL` set to private endpoint
- [ ] `POLYGON_MAINNET_RPC_URL` set to private endpoint
- [ ] `BASE_MAINNET_RPC_URL` set to private endpoint
- [ ] `BSC_MAINNET_RPC_URL` set to private endpoint
- [ ] `ARBITRUM_MAINNET_RPC_URL` set to private endpoint
- [ ] `AVALANCHE_MAINNET_RPC_URL` set to private endpoint
- [ ] RPC endpoints tested and responding

### Chain Enable/Disable
- [ ] `STELLAR_ENABLED` set correctly
- [ ] `ETHEREUM_ENABLED` set correctly
- [ ] `POLYGON_ENABLED` set correctly
- [ ] `BASE_ENABLED` set correctly
- [ ] `BSC_ENABLED` set correctly
- [ ] `ARBITRUM_ENABLED` set correctly
- [ ] `AVALANCHE_ENABLED` set correctly
- [ ] `TRON_ENABLED` set correctly
- [ ] `SOLANA_ENABLED` set correctly

---

## ✅ Phase 3: Smart Contract Deployment

### Testnet Deployment (Testing)
- [ ] Ethereum Sepolia: `npx hardhat run scripts/deploy.js --network sepolia`
- [ ] Polygon Amoy: `npx hardhat run scripts/deploy.js --network polygonAmoy`
- [ ] Base Sepolia: `npx hardhat run scripts/deploy.js --network baseSepolia`
- [ ] BSC Testnet: `npx hardhat run scripts/deploy.js --network bscTestnet`
- [ ] Arbitrum Sepolia: `npx hardhat run scripts/deploy.js --network arbitrumSepolia`
- [ ] Avalanche Fuji: `npx hardhat run scripts/deploy.js --network fuji`

### Mainnet Deployment (Production)
- [ ] Ethereum: `npx hardhat run scripts/deploy.js --network ethereum`
- [ ] Polygon: `npx hardhat run scripts/deploy.js --network polygon`
- [ ] Base: `npx hardhat run scripts/deploy.js --network base`
- [ ] BSC: `npx hardhat run scripts/deploy.js --network bsc`
- [ ] Arbitrum: `npx hardhat run scripts/deploy.js --network arbitrum`
- [ ] Avalanche: `npx hardhat run scripts/deploy.js --network avalanche`

### Contract Configuration
- [ ] `SUBSCRIPTION_CONTRACT_ETHEREUM` set in `.env`
- [ ] `SUBSCRIPTION_CONTRACT_POLYGON` set in `.env`
- [ ] `SUBSCRIPTION_CONTRACT_BASE` set in `.env`
- [ ] `SUBSCRIPTION_CONTRACT_BSC` set in `.env`
- [ ] `SUBSCRIPTION_CONTRACT_ARBITRUM` set in `.env`
- [ ] `SUBSCRIPTION_CONTRACT_AVALANCHE` set in `.env`
- [ ] Relayer address set in each contract
- [ ] USDC/USDT whitelisted in each contract
- [ ] Contracts verified on block explorers

### Non-EVM Chains (Optional)
- [ ] Soroban: `python contracts/soroban/deploy_soroban.py --network mainnet`
- [ ] Solana: `python contracts/solana/deploy_solana.py --network mainnet`
- [ ] Tron: `python contracts/tron/deploy_tron.py --network mainnet`
- [ ] Contract addresses added to `.env`

---

## ✅ Phase 4: Testing

### Wallet Generation
- [ ] Create test merchant account
- [ ] Complete onboarding with all chains
- [ ] Verify Stellar wallet is real (G... 56 chars)
- [ ] Verify EVM wallets are real (0x... 42 chars)
- [ ] Verify Solana wallet is real (base58 ~44 chars)
- [ ] No placeholder addresses generated

### Payment Flow
- [ ] Create payment session on Polygon
- [ ] Send USDC to generated wallet
- [ ] Verify listener detects payment
- [ ] Verify payment status updates to CONFIRMED
- [ ] Verify webhook notification sent
- [ ] Repeat for each enabled chain

### Refund System
- [ ] Process full refund
- [ ] Process partial refund
- [ ] Verify on-chain transaction
- [ ] Verify refund status updates
- [ ] Test queued refund (insufficient balance)
- [ ] Test force external refund

### Subscription System
- [ ] Create subscription
- [ ] Verify scheduler detects due payment
- [ ] Verify payment executed on-chain
- [ ] Verify subscription payment recorded
- [ ] Test subscription cancellation
- [ ] Test subscription pause/resume

### Invoice System
- [ ] Create invoice
- [ ] Generate PDF
- [ ] Send invoice to customer
- [ ] Verify payment link works
- [ ] Verify invoice status updates

### Webhook System
- [ ] Register webhook URL
- [ ] Verify HMAC signature
- [ ] Test webhook retry on failure
- [ ] Verify webhook delivery logs

---

## ✅ Phase 5: Security

### Authentication
- [ ] JWT tokens expire correctly (15 minutes)
- [ ] Refresh tokens work
- [ ] Password hashing uses bcrypt (cost 12)
- [ ] API keys generated securely
- [ ] Session management works

### Authorization
- [ ] Merchants can only access their own data
- [ ] Admin endpoints require admin role
- [ ] Team members have correct permissions
- [ ] Ownership verification works

### Encryption
- [ ] PII encrypted at rest (Fernet)
- [ ] Webhook signatures verified (HMAC-SHA256)
- [ ] HTTPS/TLS enabled
- [ ] Database connections encrypted

### Rate Limiting
- [ ] Rate limiting enabled
- [ ] Rate limits configured per endpoint
- [ ] Rate limit headers returned
- [ ] Blocked requests return 429

### Compliance
- [ ] GDPR data export works
- [ ] GDPR data deletion works
- [ ] Consent management works
- [ ] Audit logging enabled
- [ ] PCI-DSS requirements met

---

## ✅ Phase 6: Infrastructure

### Server Setup
- [ ] Production server provisioned
- [ ] Firewall configured (allow 80, 443, 5432)
- [ ] SSH key authentication enabled
- [ ] Root login disabled
- [ ] Fail2ban installed
- [ ] Automatic security updates enabled

### Reverse Proxy
- [ ] NGINX/Caddy installed
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] HTTPS redirect configured
- [ ] Security headers set
- [ ] Rate limiting configured
- [ ] Gzip compression enabled

### Database
- [ ] PostgreSQL tuned for production
- [ ] Connection pooling configured
- [ ] Automated backups enabled (daily)
- [ ] Backup restoration tested
- [ ] Replication configured (optional)

### Monitoring
- [ ] Prometheus/Grafana set up
- [ ] API metrics collected
- [ ] Blockchain listener metrics collected
- [ ] Database metrics collected
- [ ] Alerts configured (email/Slack)

### Logging
- [ ] Structured logging enabled
- [ ] Log rotation configured
- [ ] Log aggregation set up (ELK/Loki)
- [ ] Error tracking enabled (Sentry)
- [ ] Audit logs retained (90 days)

### Services
- [ ] API service configured (systemd)
- [ ] Blockchain listeners service configured (systemd)
- [ ] Services start on boot
- [ ] Services restart on failure
- [ ] Service logs accessible

---

## ✅ Phase 7: Performance

### API Performance
- [ ] Response time < 200ms (95th percentile)
- [ ] Database queries optimized
- [ ] Indexes created on frequently queried columns
- [ ] Caching enabled (Redis)
- [ ] Connection pooling configured

### Blockchain Performance
- [ ] Listeners poll every 10 seconds
- [ ] RPC endpoints respond < 1 second
- [ ] Payment confirmation < 5 minutes
- [ ] Webhook delivery < 10 seconds
- [ ] Refund processing < 5 minutes

### Load Testing
- [ ] API load tested (100 req/s)
- [ ] Database load tested
- [ ] Blockchain listeners tested under load
- [ ] Webhook delivery tested under load
- [ ] System stable under peak load

---

## ✅ Phase 8: Documentation

### API Documentation
- [ ] OpenAPI/Swagger docs available at `/docs`
- [ ] All endpoints documented
- [ ] Request/response examples provided
- [ ] Error codes documented
- [ ] Authentication documented

### Deployment Documentation
- [ ] `QUICK_START_GUIDE.md` reviewed
- [ ] `DEPLOYMENT_GUIDE.md` reviewed
- [ ] Environment variables documented
- [ ] Contract deployment documented
- [ ] Troubleshooting guide available

### Business Documentation
- [ ] `MVP_READINESS_ASSESSMENT.md` reviewed
- [ ] Feature list documented
- [ ] Pricing documented
- [ ] SLA defined
- [ ] Support channels defined

---

## ✅ Phase 9: Launch Preparation

### Final Checks
- [ ] All tests passing
- [ ] No critical bugs
- [ ] Performance acceptable
- [ ] Security audit passed
- [ ] Legal compliance verified

### Rollback Plan
- [ ] Database backup taken
- [ ] Previous version tagged in git
- [ ] Rollback procedure documented
- [ ] Rollback tested

### Support
- [ ] Support email configured
- [ ] Support ticket system set up
- [ ] On-call rotation defined
- [ ] Escalation procedure defined
- [ ] Status page set up

### Communication
- [ ] Launch announcement prepared
- [ ] Merchant onboarding guide prepared
- [ ] FAQ prepared
- [ ] Social media posts prepared
- [ ] Press release prepared (optional)

---

## ✅ Phase 10: Go Live

### Launch Day
- [ ] Set `USE_MAINNET=true`
- [ ] Set `ENVIRONMENT=production`
- [ ] Deploy to production server
- [ ] Start API service
- [ ] Start blockchain listeners
- [ ] Verify all services running
- [ ] Test with small real transaction
- [ ] Monitor for 1 hour
- [ ] Announce launch

### Post-Launch (First 24 Hours)
- [ ] Monitor error rates
- [ ] Monitor transaction volume
- [ ] Monitor payment confirmations
- [ ] Monitor webhook delivery
- [ ] Monitor system resources
- [ ] Respond to support requests
- [ ] Fix any critical issues

### Post-Launch (First Week)
- [ ] Review metrics daily
- [ ] Gather merchant feedback
- [ ] Fix non-critical bugs
- [ ] Optimize performance
- [ ] Update documentation
- [ ] Plan next features

---

## 🎉 Launch Complete!

Once all items are checked, you're ready to go live!

**Estimated time to complete checklist:** 6-10 hours

**Remember:**
- Start with testnets
- Test thoroughly before mainnet
- Monitor closely after launch
- Have a rollback plan ready
- Provide excellent support

Good luck! 🚀
