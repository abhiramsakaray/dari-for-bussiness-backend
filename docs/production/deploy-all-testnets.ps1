# Deploy DariSubscriptions to all testnets (PowerShell version)
# Usage: .\deploy-all-testnets.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Deploying DariSubscriptions to All Testnets" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location contracts

# Array of testnet networks
$networks = @("polygonAmoy", "sepolia", "baseSepolia", "bscTestnet", "arbitrumSepolia", "fuji")

# Deploy to each network
foreach ($network in $networks) {
    Write-Host ""
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "Deploying to $network..." -ForegroundColor Yellow
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
    
    # Check balance first
    Write-Host "Checking balance..." -ForegroundColor Cyan
    npx hardhat run scripts/check-balance.js --network $network
    
    Write-Host ""
    $response = Read-Host "Continue with deployment to $network? (y/n)"
    
    if ($response -eq "y" -or $response -eq "Y") {
        npx hardhat run scripts/deploy.js --network $network
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Successfully deployed to $network" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to deploy to $network" -ForegroundColor Red
            $continue = Read-Host "Continue with next network? (y/n)"
            if ($continue -ne "y" -and $continue -ne "Y") {
                exit 1
            }
        }
    } else {
        Write-Host "⏩ Skipping $network" -ForegroundColor Gray
    }
    
    Write-Host ""
}

Set-Location ..

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Update .env with contract addresses"
Write-Host "2. Test subscriptions on testnets"
Write-Host "3. Deploy to mainnets when ready"
Write-Host ""
