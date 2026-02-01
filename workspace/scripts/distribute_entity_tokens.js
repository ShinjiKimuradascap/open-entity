#!/usr/bin/env node
/**
 * $ENTITY Token Distribution Script
 * Entity AとBに$ENTITYトークンを配布する
 */

const { Connection, Keypair, PublicKey } = require('@solana/web3.js');
const { transfer, getOrCreateAssociatedTokenAccount, getAccount } = require('@solana/spl-token');
const fs = require('fs');
const path = require('path');

// Configuration
const MINT_ADDRESS = '3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i';
const DECIMALS = 9;

// Entity addresses (temporary - should be replaced with actual Entity A/B wallet addresses)
const ENTITIES = {
    'Entity-A': {
        name: 'Entity A',
        address: null, // Will be generated if not exists
        allocation: 100000000 // 100M tokens (10%)
    },
    'Entity-B': {
        name: 'Entity B',
        address: null, // Will be generated if not exists
        allocation: 100000000 // 100M tokens (10%)
    }
};

async function distributeTokens() {
    console.log("==============================================");
    console.log("🎯 $ENTITY Token Distribution");
    console.log("==============================================");
    
    try {
        // Connect to devnet
        const connection = new Connection('https://api.devnet.solana.com', 'confirmed');
        console.log("🔗 Connected to Solana devnet");
        
        // Load authority keypair
        const keypairPath = path.join(process.env.HOME || '/tmp', '.config', 'solana', 'entity-token.json');
        if (!fs.existsSync(keypairPath)) {
            throw new Error("Authority keypair not found. Deploy token first.");
        }
        
        const secretKey = JSON.parse(fs.readFileSync(keypairPath, 'utf8'));
        const payer = Keypair.fromSecretKey(new Uint8Array(secretKey));
        console.log(`🔑 Authority: ${payer.publicKey.toString()}`);
        
        const mint = new PublicKey(MINT_ADDRESS);
        
        // Get authority token account
        const payerTokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            payer,
            mint,
            payer.publicKey
        );
        
        // Check current balance
        const payerAccountInfo = await getAccount(connection, payerTokenAccount.address);
        const currentBalance = Number(payerAccountInfo.amount) / Math.pow(10, DECIMALS);
        console.log(`\n💰 Authority balance: ${currentBalance.toLocaleString()} $ENTITY`);
        
        // Distribute to each entity
        for (const [entityId, entity] of Object.entries(ENTITIES)) {
            console.log(`\n📤 Distributing to ${entity.name}...`);
            
            let recipientPublicKey;
            
            if (entity.address) {
                recipientPublicKey = new PublicKey(entity.address);
            } else {
                // Generate new keypair for entity
                const entityKeypair = Keypair.generate();
                recipientPublicKey = entityKeypair.publicKey;
                
                // Save entity keypair
                const entityKeyPath = path.join(
                    process.env.HOME || '/tmp', 
                    '.config', 'solana', 
                    `${entityId.toLowerCase()}-wallet.json`
                );
                fs.mkdirSync(path.dirname(entityKeyPath), { recursive: true });
                fs.writeFileSync(entityKeyPath, JSON.stringify(Array.from(entityKeypair.secretKey)));
                console.log(`  🔑 New wallet created: ${recipientPublicKey.toString()}`);
                console.log(`  💾 Saved to: ${entityKeyPath}`);
                
                // Update entity address
                entity.address = recipientPublicKey.toString();
            }
            
            // Create/get recipient token account
            const recipientTokenAccount = await getOrCreateAssociatedTokenAccount(
                connection,
                payer,
                mint,
                recipientPublicKey
            );
            
            // Transfer tokens
            const transferAmount = entity.allocation * Math.pow(10, DECIMALS);
            console.log(`  💸 Transferring ${entity.allocation.toLocaleString()} $ENTITY...`);
            
            const signature = await transfer(
                connection,
                payer,
                payerTokenAccount.address,
                recipientTokenAccount.address,
                payer,
                transferAmount
            );
            
            console.log(`  ✅ Transfer complete: ${signature}`);
            console.log(`  🔍 Explorer: https://explorer.solana.com/tx/${signature}?cluster=devnet`);
        }
        
        // Save distribution info
        const distributionInfo = {
            distributedAt: new Date().toISOString(),
            mint: MINT_ADDRESS,
            totalDistributed: Object.values(ENTITIES).reduce((sum, e) => sum + e.allocation, 0),
            entities: ENTITIES
        };
        
        const infoPath = path.join(process.cwd(), '$ENTITY_DISTRIBUTION.json');
        fs.writeFileSync(infoPath, JSON.stringify(distributionInfo, null, 2));
        
        console.log("\n==============================================");
        console.log("✅ Distribution Complete!");
        console.log("==============================================");
        console.log(`\nTotal distributed: ${distributionInfo.totalDistributed.toLocaleString()} $ENTITY`);
        console.log(`\nDistribution info saved to: ${infoPath}`);
        
    } catch (error) {
        console.error("\n❌ Distribution failed:", error.message);
        process.exit(1);
    }
}

distributeTokens();
