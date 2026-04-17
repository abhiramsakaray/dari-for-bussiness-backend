# 📚 Production Documentation

**Complete guide for deploying and launching Dari for Business Payment Gateway**

---

## 🚀 Quick Start

**New to the project? Start here:**

1. **[START_HERE.md](START_HERE.md)** ⭐ - Main entry point
2. **[DEPLOY_NOW.md](DEPLOY_NOW.md)** - Deploy contracts in 30 minutes
3. **[MANUAL_RESTART_GUIDE.md](MANUAL_RESTART_GUIDE.md)** - Restart backend

---

## 📋 Documentation Index

### 🎯 Getting Started
| Document | Description | When to Use |
|----------|-------------|-------------|
| **[START_HERE.md](START_HERE.md)** | Main entry point with quick start | First time setup |
| **[LAUNCH_READY_SUMMARY.md](LAUNCH_READY_SUMMARY.md)** | Executive summary of what's ready | Quick overview |
| **[MVP_READINESS_ASSESSMENT.md](MVP_READINESS_ASSESSMENT.md)** | Complete feature audit | Understand what's implemented |

### 🚢 Deployment Guides
| Document | Description | When to Use |
|----------|-------------|-------------|
| **[DEPLOY_NOW.md](DEPLOY_NOW.md)** | Quick 30-minute deployment | Deploy contracts to testnets |
| **[DEPLOY_CONTRACTS_GUIDE.md](DEPLOY_CONTRACTS_GUIDE.md)** | Detailed deployment docs | Full deployment reference |
| **[QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)** | Complete setup guide | End-to-end deployment |
| **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** | Technical implementation details | Understand the architecture |

### ✅ Pre-Launch
| Document | Description | When to Use |
|----------|-------------|-------------|
| **[PRE_LAUNCH_CHECKLIST.md](PRE_LAUNCH_CHECKLIST.md)** | Complete pre-launch checklist | Before going live |

### 🗄️ Database Setup
| File | Description | When to Use |
|------|-------------|-------------|
| **[FINAL_COMPLETE_SCHEMA.sql](FINAL_COMPLETE_SCHEMA.sql)** | Complete database schema | Fresh database setup |
| **[FINAL_FIX.sql](FINAL_FIX.sql)** | Critical database fixes | After migration |
| **[DATABASE_MIGRATION_COMPLETE.md](DATABASE_MIGRATION_COMPLETE.md)** | Migration status & guide | Post-migration reference |
| **[CHECK_TABLE_STRUCTURE.sql](CHECK_TABLE_STRUCTURE.sql)** | Diagnostic queries | Troubleshooting |
| **[FIX_DATABASE_ISSUES.sql](FIX_DATABASE_ISSUES.sql)** | Fix common issues | Database errors |

### 🔄 Backend Management
| File | Description | When to Use |
|------|-------------|-------------|
| **[MANUAL_RESTART_GUIDE.md](MANUAL_RESTART_GUIDE.md)** | Manual restart instructions | Restart backend |
| **[find_and_restart_backend.sh](find_and_restart_backend.sh)** | Automated restart script | Quick restart |
| **[RESTART_BACKEND.sh](RESTART_BACKEND.sh)** | Systemd restart script | Systemd environments |

### 📜 Deployment Scripts
| File | Description | When to Use |
|------|-------------|-------------|
| **[deploy-all-testnets.sh](deploy-all-testnets.sh)** | Deploy to all testnets (Linux/Mac) | Automated testnet deployment |
| **[deploy-all-testnets.ps1](deploy-all-testnets.ps1)** | Deploy to all testnets (Windows) | Automated testnet deployment |
| **[deploy-all-mainnets.sh](deploy-all-mainnets.sh)** | Deploy to all mainnets | Production deployment |

---

## 🎯 Common Tasks

### First Time Setup
1. Read **START_HERE.md**
2. Follow **DEPLOY_NOW.md**
3. Run **FINAL_COMPLETE_SCHEMA.sql**
4. Use **MANUAL_RESTART_GUIDE.md**

### Deploy Smart Contracts
1. **Testnets:** Run `deploy-all-testnets.sh`
2. **Mainnets:** Run `deploy-all-mainnets.sh`
3. Or follow **DEPLOY_CONTRACTS_GUIDE.md** for manual deployment

### Database Setup
1. Fresh install: Run **FINAL_COMPLETE_SCHEMA.sql**
2. After migration: Run **FINAL_FIX.sql**
3. Check status: **DATABASE_MIGRATION_COMPLETE.md**

### Restart Backend
1. Quick: Run `find_and_restart_backend.sh`
2. Manual: Follow **MANUAL_RESTART_GUIDE.md**
3. Systemd: Use **RESTART_BACKEND.sh**

### Pre-Launch
1. Complete **PRE_LAUNCH_CHECKLIST.md**
2. Review **MVP_READINESS_ASSESSMENT.md**
3. Check **LAUNCH_READY_SUMMARY.md**

---

## 📊 Project Status

### ✅ Phase 1 - MVP: 100% Complete
- Multi-chain payments
- Payment links
- Hosted checkout
- Transaction monitoring
- Merchant authentication
- Wallet generation
- API documentation

### ✅ Phase 2 - Automation: 100% Complete
- Recurring payments
- Subscription management
- Invoice generation
- Webhooks
- Refund system
- Rate limiting
- Fraud monitoring

### 🌐 Supported Blockchains
- Stellar ✅
- Ethereum ✅
- Polygon ✅
- Base ✅
- BSC ✅
- Arbitrum ✅
- Avalanche ✅
- Tron ✅
- Solana ⚠️ (partial)

---

## 🔧 Quick Commands

### Database
```bash
# Run complete schema
psql "postgresql://user:pass@localhost:5432/chainpe" -f FINAL_COMPLETE_SCHEMA.sql

# Run fixes
psql "postgresql://user:pass@localhost:5432/chainpe" -f FINAL_FIX.sql

# Check structure
psql "postgresql://user:pass@localhost:5432/chainpe" -f CHECK_TABLE_STRUCTURE.sql
```

### Backend
```bash
# Automated restart
./find_and_restart_backend.sh

# Manual restart
pkill -f uvicorn
cd ~/dari-for-bussiness-backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Contracts
```bash
# Deploy to testnets
./deploy-all-testnets.sh

# Deploy to mainnets
./deploy-all-mainnets.sh

# Deploy single chain
cd contracts
npx hardhat run scripts/deploy.js --network polygon
```

---

## 📞 Need Help?

### Common Issues
1. **Database errors:** Check DATABASE_MIGRATION_COMPLETE.md
2. **Backend won't start:** Follow MANUAL_RESTART_GUIDE.md
3. **Contract deployment fails:** See DEPLOY_CONTRACTS_GUIDE.md
4. **Missing features:** Review MVP_READINESS_ASSESSMENT.md

### Troubleshooting
- Check logs: `tail -f ~/dari-for-bussiness-backend/dari.log`
- Test database: `psql "postgresql://user:pass@localhost:5432/chainpe" -c "SELECT 1;"`
- Test API: `curl http://localhost:8000/docs`

---

## 📝 File Organization

```
docs/production/
├── README.md (this file)
│
├── Getting Started
│   ├── START_HERE.md
│   ├── LAUNCH_READY_SUMMARY.md
│   └── MVP_READINESS_ASSESSMENT.md
│
├── Deployment
│   ├── DEPLOY_NOW.md
│   ├── DEPLOY_CONTRACTS_GUIDE.md
│   ├── QUICK_START_GUIDE.md
│   └── IMPLEMENTATION_COMPLETE.md
│
├── Database
│   ├── FINAL_COMPLETE_SCHEMA.sql
│   ├── FINAL_FIX.sql
│   ├── DATABASE_MIGRATION_COMPLETE.md
│   ├── CHECK_TABLE_STRUCTURE.sql
│   └── FIX_DATABASE_ISSUES.sql
│
├── Backend Management
│   ├── MANUAL_RESTART_GUIDE.md
│   ├── find_and_restart_backend.sh
│   └── RESTART_BACKEND.sh
│
├── Scripts
│   ├── deploy-all-testnets.sh
│   ├── deploy-all-testnets.ps1
│   └── deploy-all-mainnets.sh
│
└── Checklists
    └── PRE_LAUNCH_CHECKLIST.md
```

---

## 🎉 Ready to Launch?

1. ✅ Complete PRE_LAUNCH_CHECKLIST.md
2. ✅ Deploy contracts (DEPLOY_NOW.md)
3. ✅ Setup database (FINAL_COMPLETE_SCHEMA.sql)
4. ✅ Start backend (MANUAL_RESTART_GUIDE.md)
5. 🚀 Go live!

---

**Last Updated:** April 17, 2026  
**Version:** 2.2.0  
**Status:** Production Ready
