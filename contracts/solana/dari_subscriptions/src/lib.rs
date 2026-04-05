use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

declare_id!("DariSubs11111111111111111111111111111111111");

/// Dari for Business — Solana Subscription Program
///
/// Implements recurring pull-payments using SPL Token delegated approval.
///
/// Flow:
///   1. Subscriber calls SPL Token `approve()` delegating tokens to their
///      subscription PDA (or directly to the relayer — see execute_payment).
///   2. Relayer calls `create_subscription` to register on-chain state.
///   3. Scheduler detects due payments; relayer calls `execute_payment`.
///   4. Program transfers tokens from subscriber ATA → merchant ATA using
///      the delegate authority stored in the subscription PDA.
#[program]
pub mod dari_subscriptions {
    use super::*;

    /// One-time initialization of the global config account.
    pub fn initialize(ctx: Context<Initialize>, relayer: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.admin = ctx.accounts.admin.key();
        config.relayer = relayer;
        config.subscription_count = 0;
        config.paused = false;
        Ok(())
    }

    /// Update the relayer address. Only admin.
    pub fn set_relayer(ctx: Context<AdminAction>, new_relayer: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.relayer = new_relayer;
        Ok(())
    }

    /// Pause / unpause the program. Only admin.
    pub fn set_paused(ctx: Context<AdminAction>, paused: bool) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.paused = paused;
        Ok(())
    }

    /// Create a new subscription.
    ///
    /// The subscriber must have previously called `spl_token::approve` to
    /// delegate at least `amount` of the token to this program's PDA or
    /// to the relayer wallet.
    pub fn create_subscription(
        ctx: Context<CreateSubscription>,
        subscription_id: u64,
        amount: u64,
        interval: i64,
        start_time: i64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(!config.paused, DariError::ContractPaused);
        require!(
            ctx.accounts.authority.key() == config.relayer,
            DariError::OnlyRelayer
        );
        require!(amount > 0, DariError::InvalidAmount);
        require!(interval >= 3600, DariError::InvalidInterval);

        let clock = Clock::get()?;
        require!(start_time >= clock.unix_timestamp, DariError::InvalidStartTime);

        // Verify subscriber has sufficient delegated allowance
        let subscriber_ata = &ctx.accounts.subscriber_token_account;
        require!(
            subscriber_ata.delegated_amount >= amount,
            DariError::InsufficientAllowance
        );
        require!(
            subscriber_ata.amount >= amount,
            DariError::InsufficientBalance
        );

        let sub = &mut ctx.accounts.subscription;
        sub.id = subscription_id;
        sub.subscriber = ctx.accounts.subscriber.key();
        sub.merchant = ctx.accounts.merchant.key();
        sub.mint = ctx.accounts.mint.key();
        sub.amount = amount;
        sub.interval = interval;
        sub.next_payment = start_time;
        sub.payment_count = 0;
        sub.active = true;
        sub.created_at = clock.unix_timestamp;
        sub.bump = ctx.bumps.subscription;

        // Increment global counter
        let config = &mut ctx.accounts.config;
        config.subscription_count += 1;

        emit!(SubscriptionCreated {
            subscription_id,
            subscriber: sub.subscriber,
            merchant: sub.merchant,
            mint: sub.mint,
            amount,
            interval,
            start_time,
        });

        Ok(())
    }

    /// Execute a due payment. Only callable by relayer.
    ///
    /// Transfers `amount` tokens from subscriber ATA → merchant ATA
    /// using the subscriber's delegated approval to the relayer.
    pub fn execute_payment(ctx: Context<ExecutePayment>) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(!config.paused, DariError::ContractPaused);
        require!(
            ctx.accounts.authority.key() == config.relayer,
            DariError::OnlyRelayer
        );

        let sub = &mut ctx.accounts.subscription;
        require!(sub.active, DariError::SubscriptionNotActive);
        require!(sub.amount > 0, DariError::InvalidAmount);

        let clock = Clock::get()?;
        require!(
            clock.unix_timestamp >= sub.next_payment,
            DariError::PaymentNotDue
        );

        // Verify allowance and balance
        let subscriber_ata = &ctx.accounts.subscriber_token_account;
        require!(
            subscriber_ata.delegated_amount >= sub.amount,
            DariError::InsufficientAllowance
        );
        require!(
            subscriber_ata.amount >= sub.amount,
            DariError::InsufficientBalance
        );

        // Update state BEFORE transfer (CEI pattern)
        sub.payment_count += 1;
        sub.next_payment = clock.unix_timestamp + sub.interval;

        // Transfer tokens: subscriber ATA → merchant ATA
        // The relayer is the delegate on the subscriber's ATA
        let transfer_ctx = CpiContext::new(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.subscriber_token_account.to_account_info(),
                to: ctx.accounts.merchant_token_account.to_account_info(),
                authority: ctx.accounts.authority.to_account_info(),
            },
        );
        token::transfer(transfer_ctx, sub.amount)?;

        emit!(PaymentExecuted {
            subscription_id: sub.id,
            subscriber: sub.subscriber,
            merchant: sub.merchant,
            amount: sub.amount,
            timestamp: clock.unix_timestamp,
            payment_number: sub.payment_count,
        });

        Ok(())
    }

    /// Cancel a subscription.
    /// Callable by subscriber, merchant, relayer, or admin.
    pub fn cancel_subscription(ctx: Context<CancelSubscription>) -> Result<()> {
        let sub = &mut ctx.accounts.subscription;
        require!(sub.active, DariError::SubscriptionNotActive);

        let caller = ctx.accounts.authority.key();
        let config = &ctx.accounts.config;

        require!(
            caller == sub.subscriber
                || caller == sub.merchant
                || caller == config.relayer
                || caller == config.admin,
            DariError::NotAuthorizedToCancel
        );

        sub.active = false;

        let clock = Clock::get()?;
        emit!(SubscriptionCancelled {
            subscription_id: sub.id,
            cancelled_by: caller,
            timestamp: clock.unix_timestamp,
        });

        Ok(())
    }

    /// Update subscription amount/interval. Only relayer.
    /// Amount can only decrease.
    pub fn update_subscription(
        ctx: Context<UpdateSubscription>,
        new_amount: u64,
        new_interval: i64,
    ) -> Result<()> {
        let config = &ctx.accounts.config;
        require!(!config.paused, DariError::ContractPaused);
        require!(
            ctx.accounts.authority.key() == config.relayer,
            DariError::OnlyRelayer
        );

        let sub = &mut ctx.accounts.subscription;
        require!(sub.active, DariError::SubscriptionNotActive);
        require!(new_amount > 0, DariError::InvalidAmount);
        require!(new_interval >= 3600, DariError::InvalidInterval);
        require!(new_amount <= sub.amount, DariError::AmountCannotIncrease);

        let old_amount = sub.amount;
        let old_interval = sub.interval;

        sub.amount = new_amount;
        sub.interval = new_interval;

        emit!(SubscriptionUpdated {
            subscription_id: sub.id,
            old_amount,
            new_amount,
            old_interval,
            new_interval,
        });

        Ok(())
    }
}

// ============= ACCOUNTS =============

#[account]
pub struct Config {
    pub admin: Pubkey,
    pub relayer: Pubkey,
    pub subscription_count: u64,
    pub paused: bool,
}

impl Config {
    pub const SIZE: usize = 8 + 32 + 32 + 8 + 1; // discriminator + fields
}

#[account]
pub struct SubscriptionAccount {
    pub id: u64,
    pub subscriber: Pubkey,
    pub merchant: Pubkey,
    pub mint: Pubkey,
    pub amount: u64,
    pub interval: i64,
    pub next_payment: i64,
    pub payment_count: u32,
    pub active: bool,
    pub created_at: i64,
    pub bump: u8,
}

impl SubscriptionAccount {
    // discriminator(8) + id(8) + subscriber(32) + merchant(32) + mint(32) +
    // amount(8) + interval(8) + next_payment(8) + payment_count(4) + active(1) +
    // created_at(8) + bump(1) = 150
    pub const SIZE: usize = 8 + 8 + 32 + 32 + 32 + 8 + 8 + 8 + 4 + 1 + 8 + 1;
}

// ============= INSTRUCTION CONTEXTS =============

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = admin,
        space = Config::SIZE,
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub admin: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AdminAction<'info> {
    #[account(
        mut,
        seeds = [b"config"],
        bump,
        has_one = admin,
    )]
    pub config: Account<'info, Config>,

    pub admin: Signer<'info>,
}

#[derive(Accounts)]
#[instruction(subscription_id: u64)]
pub struct CreateSubscription<'info> {
    #[account(
        mut,
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(
        init,
        payer = authority,
        space = SubscriptionAccount::SIZE,
        seeds = [b"subscription", subscriber.key().as_ref(), &subscription_id.to_le_bytes()],
        bump,
    )]
    pub subscription: Account<'info, SubscriptionAccount>,

    /// The relayer wallet (pays for account creation)
    #[account(mut)]
    pub authority: Signer<'info>,

    /// CHECK: Subscriber public key, validated by business logic
    pub subscriber: AccountInfo<'info>,

    /// CHECK: Merchant public key, validated by business logic
    pub merchant: AccountInfo<'info>,

    /// CHECK: SPL Token mint, validated by token account constraints
    pub mint: AccountInfo<'info>,

    /// Subscriber's token account (ATA) — must be for the correct mint and subscriber
    #[account(
        constraint = subscriber_token_account.owner == subscriber.key(),
        constraint = subscriber_token_account.mint == mint.key(),
    )]
    pub subscriber_token_account: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ExecutePayment<'info> {
    #[account(
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(
        mut,
        seeds = [b"subscription", subscription.subscriber.as_ref(), &subscription.id.to_le_bytes()],
        bump = subscription.bump,
    )]
    pub subscription: Account<'info, SubscriptionAccount>,

    /// The relayer wallet — must be the delegate on subscriber_token_account
    pub authority: Signer<'info>,

    #[account(
        mut,
        constraint = subscriber_token_account.owner == subscription.subscriber,
        constraint = subscriber_token_account.mint == subscription.mint,
    )]
    pub subscriber_token_account: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = merchant_token_account.owner == subscription.merchant,
        constraint = merchant_token_account.mint == subscription.mint,
    )]
    pub merchant_token_account: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
pub struct CancelSubscription<'info> {
    #[account(
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub subscription: Account<'info, SubscriptionAccount>,

    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct UpdateSubscription<'info> {
    #[account(
        seeds = [b"config"],
        bump,
    )]
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub subscription: Account<'info, SubscriptionAccount>,

    pub authority: Signer<'info>,
}

// ============= EVENTS =============

#[event]
pub struct SubscriptionCreated {
    pub subscription_id: u64,
    pub subscriber: Pubkey,
    pub merchant: Pubkey,
    pub mint: Pubkey,
    pub amount: u64,
    pub interval: i64,
    pub start_time: i64,
}

#[event]
pub struct PaymentExecuted {
    pub subscription_id: u64,
    pub subscriber: Pubkey,
    pub merchant: Pubkey,
    pub amount: u64,
    pub timestamp: i64,
    pub payment_number: u32,
}

#[event]
pub struct SubscriptionCancelled {
    pub subscription_id: u64,
    pub cancelled_by: Pubkey,
    pub timestamp: i64,
}

#[event]
pub struct SubscriptionUpdated {
    pub subscription_id: u64,
    pub old_amount: u64,
    pub new_amount: u64,
    pub old_interval: i64,
    pub new_interval: i64,
}

// ============= ERRORS =============

#[error_code]
pub enum DariError {
    #[msg("Only the relayer can perform this action")]
    OnlyRelayer,
    #[msg("Invalid address")]
    InvalidAddress,
    #[msg("Amount must be greater than zero")]
    InvalidAmount,
    #[msg("Interval must be at least 3600 seconds (1 hour)")]
    InvalidInterval,
    #[msg("Start time must be in the future")]
    InvalidStartTime,
    #[msg("Subscription is not active")]
    SubscriptionNotActive,
    #[msg("Payment is not yet due")]
    PaymentNotDue,
    #[msg("Insufficient token allowance (delegation)")]
    InsufficientAllowance,
    #[msg("Insufficient token balance")]
    InsufficientBalance,
    #[msg("Not authorized to cancel this subscription")]
    NotAuthorizedToCancel,
    #[msg("Amount cannot be increased — create a new subscription")]
    AmountCannotIncrease,
    #[msg("Contract is paused")]
    ContractPaused,
}
