#!/usr/bin/env node
/**
 * Solana Bridge - SPL Token Transfer Module
 * 
 * Bridges internal JSON token system with Solana blockchain
 * Uses @solana/web3.js and @solana/spl-token
 */

const { Connection, PublicKey, Keypair, Transaction, sendAndConfirmTransaction } = require('@solana/web3.js');
const { getOrCreateAssociatedTokenAccount, createTransferInstruction, getAccount } = require('@solana/spl-token');
const fs = require('fs');
const path = require('path');

// Configuration
const SOLANA_RPC = process.env.SOLANA_RPC || 'https://api.devnet.solana.com';
const TOKEN_MINT = process.env.ENTITY_TOKEN_MINT || '3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i';
const DECIMALS = 9;

// Wallet storage path
const WALLET_DIR = path.join(__dirname, '..', 'data', 'solana_wallets');

// Ensure wallet directory exists
if (!fs.existsSync(WALLET_DIR)) {
    fs.mkdirSync(WALLET_DIR, { recursive: true });
}

/**
 * Get or create a Keypair for an entity
 */
function getEntityKeypair(entityId) {
    const walletPath = path.join(WALLET_DIR, `${entityId}.json`);
    
    if (fs.existsSync(walletPath)) {
        // Load existing wallet
        const secretKey = JSON.parse(fs.readFileSync(walletPath, 'utf-8'));
        return Keypair.fromSecretKey(new Uint8Array(secretKey));
    }
    
    // Create new wallet
    const keypair = Keypair.generate();
    fs.writeFileSync(walletPath, JSON.stringify(Array.from(keypair.secretKey)));
    console.log(`Created new Solana wallet for ${entityId}: ${keypair.publicKey.toBase58()}`);
    
    return keypair;
}

/**
 * Get public key for an entity
 */
function getEntityPublicKey(entityId) {
    const keypair = getEntityKeypair(entityId);
    return keypair.publicKey.toBase58();
}

/**
 * Transfer SPL tokens between entities
 */
async function transferTokens(fromEntity, toEntity, amount, orderId = '') {
    try {
        const connection = new Connection(SOLANA_RPC, 'confirmed');
        const mintPublicKey = new PublicKey(TOKEN_MINT);
        
        // Get sender keypair
        const fromKeypair = getEntityKeypair(fromEntity);
        console.log(`Sender: ${fromKeypair.publicKey.toBase58()}`);
        
        // Get recipient public key (create wallet if needed)
        const toKeypair = getEntityKeypair(toEntity);
        const toPublicKey = toKeypair.publicKey;
        console.log(`Recipient: ${toPublicKey.toBase58()}`);
        
        // Get or create token accounts
        const fromTokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            fromKeypair, // payer
            mintPublicKey,
            fromKeypair.publicKey // owner
        );
        
        const toTokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            fromKeypair, // payer
            mintPublicKey,
            toPublicKey // owner
        );
        
        // Convert amount to lamports (considering decimals)
        const amountLamports = Math.floor(amount * Math.pow(10, DECIMALS));
        console.log(`Transferring ${amount} tokens (${amountLamports} lamports)`);
        
        // Create transfer instruction
        const transferInstruction = createTransferInstruction(
            fromTokenAccount.address,
            toTokenAccount.address,
            fromKeypair.publicKey,
            amountLamports
        );
        
        // Build and send transaction
        const transaction = new Transaction().add(transferInstruction);
        const signature = await sendAndConfirmTransaction(
            connection,
            transaction,
            [fromKeypair]
        );
        
        console.log(`Transfer successful! Signature: ${signature}`);
        console.log(`Explorer: https://explorer.solana.com/tx/${signature}?cluster=devnet`);
        
        return {
            success: true,
            signature: signature,
            from: fromKeypair.publicKey.toBase58(),
            to: toPublicKey.toBase58(),
            amount: amount,
            order_id: orderId,
            explorer_url: `https://explorer.solana.com/tx/${signature}?cluster=devnet`
        };
        
    } catch (error) {
        console.error('Transfer failed:', error.message);
        return {
            success: false,
            error: error.message,
            from: fromEntity,
            to: toEntity,
            amount: amount
        };
    }
}

/**
 * Get token balance for an entity
 */
async function getTokenBalance(entityId) {
    try {
        const connection = new Connection(SOLANA_RPC, 'confirmed');
        const mintPublicKey = new PublicKey(TOKEN_MINT);
        const keypair = getEntityKeypair(entityId);
        
        try {
            const tokenAccount = await getOrCreateAssociatedTokenAccount(
                connection,
                keypair,
                mintPublicKey,
                keypair.publicKey
            );
            
            const accountInfo = await getAccount(connection, tokenAccount.address);
            const balance = Number(accountInfo.amount) / Math.pow(10, DECIMALS);
            
            return {
                success: true,
                entity_id: entityId,
                public_key: keypair.publicKey.toBase58(),
                token_account: tokenAccount.address.toBase58(),
                balance: balance,
                raw_amount: accountInfo.amount.toString()
            };
        } catch (e) {
            // Account doesn't exist yet
            return {
                success: true,
                entity_id: entityId,
                public_key: keypair.publicKey.toBase58(),
                token_account: null,
                balance: 0,
                raw_amount: '0'
            };
        }
        
    } catch (error) {
        return {
            success: false,
            error: error.message,
            entity_id: entityId
        };
    }
}

/**
 * Request airdrop for testing (devnet only)
 */
async function requestAirdrop(entityId, amountSol = 1) {
    try {
        const connection = new Connection(SOLANA_RPC, 'confirmed');
        const keypair = getEntityKeypair(entityId);
        
        const lamports = amountSol * 1000000000; // 1 SOL = 10^9 lamports
        const signature = await connection.requestAirdrop(keypair.publicKey, lamports);
        
        await connection.confirmTransaction(signature);
        
        return {
            success: true,
            signature: signature,
            amount_sol: amountSol,
            public_key: keypair.publicKey.toBase58()
        };
        
    } catch (error) {
        return {
            success: false,
            error: error.message
        };
    }
}

// CLI interface
async function main() {
    const args = process.argv.slice(2);
    const command = args[0];
    
    switch (command) {
        case 'transfer':
            // Usage: node solana_bridge.js transfer <from_entity> <to_entity> <amount> [order_id]
            if (args.length < 4) {
                console.error('Usage: transfer <from_entity> <to_entity> <amount> [order_id]');
                process.exit(1);
            }
            const result = await transferTokens(args[1], args[2], parseFloat(args[3]), args[4] || '');
            console.log(JSON.stringify(result, null, 2));
            break;
            
        case 'balance':
            // Usage: node solana_bridge.js balance <entity_id>
            if (args.length < 2) {
                console.error('Usage: balance <entity_id>');
                process.exit(1);
            }
            const balanceResult = await getTokenBalance(args[1]);
            console.log(JSON.stringify(balanceResult, null, 2));
            break;
            
        case 'airdrop':
            // Usage: node solana_bridge.js airdrop <entity_id> [amount_sol]
            if (args.length < 2) {
                console.error('Usage: airdrop <entity_id> [amount_sol]');
                process.exit(1);
            }
            const airdropResult = await requestAirdrop(args[1], parseFloat(args[2] || '1'));
            console.log(JSON.stringify(airdropResult, null, 2));
            break;
            
        case 'address':
            // Usage: node solana_bridge.js address <entity_id>
            if (args.length < 2) {
                console.error('Usage: address <entity_id>');
                process.exit(1);
            }
            const pubKey = getEntityPublicKey(args[1]);
            console.log(JSON.stringify({
                entity_id: args[1],
                public_key: pubKey,
                token_mint: TOKEN_MINT
            }, null, 2));
            break;
            
        default:
            console.log('Solana Bridge - SPL Token Management');
            console.log('');
            console.log('Commands:');
            console.log('  transfer <from_entity> <to_entity> <amount> [order_id]  - Transfer tokens');
            console.log('  balance <entity_id>                                      - Check balance');
            console.log('  airdrop <entity_id> [amount_sol]                         - Request SOL airdrop (devnet)');
            console.log('  address <entity_id>                                      - Get public address');
            console.log('');
            console.log('Environment:');
            console.log(`  SOLANA_RPC: ${SOLANA_RPC}`);
            console.log(`  TOKEN_MINT: ${TOKEN_MINT}`);
            process.exit(1);
    }
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

// Export for use as module
module.exports = {
    transferTokens,
    getTokenBalance,
    requestAirdrop,
    getEntityKeypair,
    getEntityPublicKey
};
