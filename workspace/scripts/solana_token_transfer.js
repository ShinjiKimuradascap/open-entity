#!/usr/bin/env node
/**
 * Solana SPL Token Transfer Script
 * 
 * Usage:
 *   node solana_token_transfer.js <sender_private_key> <recipient_address> <amount> [token_mint]
 * 
 * Environment Variables:
 *   SOLANA_RPC_URL - Solana RPC endpoint (default: https://api.devnet.solana.com)
 *   TOKEN_MINT - Default token mint address
 */

const { Connection, Keypair, PublicKey, Transaction, sendAndConfirmTransaction } = require('@solana/web3.js');
const { createTransferInstruction, getAssociatedTokenAddress, getOrCreateAssociatedTokenAccount } = require('@solana/spl-token');
const bs58 = require('bs58');

// Configuration
const RPC_URL = process.env.SOLANA_RPC_URL || 'https://api.devnet.solana.com';
const TOKEN_MINT = process.env.TOKEN_MINT || '3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i';
const DECIMALS = 9; // $ENTITY token decimals

async function transferTokens(senderPrivateKey, recipientAddress, amount, tokenMint = TOKEN_MINT) {
    try {
        // Setup connection
        const connection = new Connection(RPC_URL, 'confirmed');
        
        // Decode sender keypair
        let senderKeypair;
        try {
            // Try base58 encoded private key
            const secretKey = bs58.decode(senderPrivateKey);
            senderKeypair = Keypair.fromSecretKey(secretKey);
        } catch (e) {
            // Try JSON array format
            try {
                const secretKey = new Uint8Array(JSON.parse(senderPrivateKey));
                senderKeypair = Keypair.fromSecretKey(secretKey);
            } catch (e2) {
                throw new Error(`Invalid private key format: ${e.message}`);
            }
        }
        
        const senderPublicKey = senderKeypair.publicKey;
        
        // Validate recipient address
        let recipientPublicKey;
        try {
            recipientPublicKey = new PublicKey(recipientAddress);
        } catch (e) {
            throw new Error(`Invalid recipient address: ${e.message}`);
        }
        
        // Token mint
        const mintPublicKey = new PublicKey(tokenMint);
        
        // Get or create sender's token account
        const senderTokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            senderKeypair,
            mintPublicKey,
            senderPublicKey
        );
        
        // Get or create recipient's token account
        const recipientTokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            senderKeypair,
            mintPublicKey,
            recipientPublicKey
        );
        
        // Convert amount to token units (considering decimals)
        const tokenAmount = BigInt(Math.floor(amount * Math.pow(10, DECIMALS)));
        
        // Create transfer instruction
        const transferInstruction = createTransferInstruction(
            senderTokenAccount.address,
            recipientTokenAccount.address,
            senderPublicKey,
            tokenAmount
        );
        
        // Create and sign transaction
        const transaction = new Transaction().add(transferInstruction);
        
        // Get recent blockhash
        const { blockhash } = await connection.getLatestBlockhash();
        transaction.recentBlockhash = blockhash;
        transaction.feePayer = senderPublicKey;
        
        // Send transaction
        const signature = await sendAndConfirmTransaction(
            connection,
            transaction,
            [senderKeypair],
            {
                commitment: 'confirmed',
                preflightCommitment: 'confirmed'
            }
        );
        
        // Return success result
        const result = {
            success: true,
            signature: signature,
            sender: senderPublicKey.toString(),
            recipient: recipientAddress,
            amount: amount,
            token_mint: tokenMint,
            explorer_url: `https://explorer.solana.com/tx/${signature}?cluster=devnet`
        };
        
        console.log(JSON.stringify(result, null, 2));
        return result;
        
    } catch (error) {
        const result = {
            success: false,
            error: error.message,
            sender: senderPrivateKey ? '[REDACTED]' : null,
            recipient: recipientAddress,
            amount: amount
        };
        console.error(JSON.stringify(result, null, 2));
        process.exit(1);
    }
}

// Main execution
if (require.main === module) {
    const args = process.argv.slice(2);
    
    if (args.length < 3) {
        console.error('Usage: node solana_token_transfer.js <sender_private_key> <recipient_address> <amount> [token_mint]');
        console.error('Environment: SOLANA_RPC_URL, TOKEN_MINT');
        process.exit(1);
    }
    
    const [senderPrivateKey, recipientAddress, amountStr, tokenMint] = args;
    const amount = parseFloat(amountStr);
    
    if (isNaN(amount) || amount <= 0) {
        console.error(JSON.stringify({
            success: false,
            error: 'Invalid amount. Must be a positive number.'
        }));
        process.exit(1);
    }
    
    transferTokens(senderPrivateKey, recipientAddress, amount, tokenMint);
}

module.exports = { transferTokens };
