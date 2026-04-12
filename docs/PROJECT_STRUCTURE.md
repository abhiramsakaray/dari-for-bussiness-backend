# Project Structure

## Root Directory
The root directory contains only essential files for the project:

- `README.md` - Project documentation
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variables template
- `.gitignore` - Git ignore rules

## Directory Structure

```
dari-payment-gateway/
├── app/                    # Main application code
│   ├── core/              # Core functionality (auth, database, middleware)
│   ├── models/            # Database models
│   ├── routes/            # API endpoints
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # Business logic services
│   └── templates/         # HTML templates
│
├── contracts/             # Smart contracts
│   ├── src/              # Solidity contracts (EVM)
│   ├── solana/           # Solana/Anchor contracts
│   ├── soroban/          # Stellar Soroban contracts
│   └── tron/             # Tron contracts
│
├── docs/                  # Documentation
│   ├── blockchain/       # Blockchain integration docs
│   ├── enterprise/       # Enterprise features docs
│   ├── frontend/         # Frontend integration guides
│   └── team/             # Team management & RBAC docs
│
├── migrations/            # Database migrations (Alembic)
│
├── public/                # Static files (SDK, demos)
│
├── scripts/               # Utility scripts
│   ├── example_team_middleware_usage.py
│   ├── force_retry_refunds.py
│   └── reset_and_reprocess_refunds.py
│
└── tests/                 # Test files
    ├── test_team_auth_verification.py
    ├── test_receipt_generation.py
    ├── test_team_auth_db_functions.py
    ├── test_team_middleware.py
    └── test_instant_vs_scheduled.py
```

## Documentation Organization

### `/docs/blockchain/`
- Blockchain listener documentation
- Deployment guides
- Smart contract documentation
- Subscription contract guides

### `/docs/enterprise/`
- Enterprise features
- Infrastructure documentation
- Pricing and features
- Local currency balance

### `/docs/frontend/`
- Frontend integration guides
- API endpoint documentation
- React integration examples
- Coupon and onboarding guides

### `/docs/team/`
- Team management documentation
- RBAC implementation guides
- Team member onboarding
- Frontend integration for team features
- Quick reference guides

### `/docs/` (root level)
- General implementation summaries
- Feature summaries
- Receipt generation guides
- Refund documentation

## Scripts

All utility scripts are in `/scripts/`:
- Database maintenance scripts
- Example usage scripts
- Refund processing utilities

## Tests

All test files are in `/tests/`:
- Unit tests
- Integration tests
- Feature-specific tests

## Git Ignore

The `.gitignore` file excludes:
- Environment files (`.env`)
- Python cache files (`__pycache__/`, `*.pyc`)
- Virtual environments (`venv/`, `env/`)
- Log files (`*.log`)
- Database files (`*.sqlite`)
- IDE files (`.vscode/`, `.idea/`)
- OS files (`.DS_Store`, `Thumbs.db`)

## Important Notes

1. **Never commit `.env` files** - Use `.env.example` as a template
2. **Log files are ignored** - They should not be committed to git
3. **Keep root clean** - Only essential configuration files in root
4. **Organize by feature** - Related docs go in appropriate subdirectories
5. **Tests separate** - All test files in `/tests/` directory
