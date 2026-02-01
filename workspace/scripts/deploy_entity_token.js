#!/usr/bin/env node
/**
 * $ENTITY Token Deployment Script for Solana (Node.js version)
 * Solana devnetに$ENTITYトークンをデプロイする
 */

const { Connection, Keypair, clusterApiUrl, PublicKey } = require('@solana/web3.js');
const { createMint, mintTo, getOrCreateAssociatedTokenAccount, getMint } = require('@solana/spl-token');
const fs = require('fs');
const path = require('path');

// Configuration
const TOKEN_NAME = "ENTITY Token";
const TOKEN_SYMBOL = "ENTITY";
const DECIMALS = 9;
const TOTAL_SUPPLY = 1000000000; // 1 billion

async function deployEntityToken() {
    console.log("==============================================");
    console.log("🚀 $ENTITY Token Solana Deployment (Node.js)");
    console.log("==============================================");
    
    try {
        // Connect to devnet with multiple fallback options
        const DEVNET_RPCS = [
            'https://api.devnet.solana.com',
            'https://devnet.helius-rpc.com/?api-key=1d7a50f4-b82a-4c0e-9ce3-8e5b7b6b2847',
            'https://solana-devnet.g.alchemy.com/v2/demo',
        ];
        
        let connection;
        for (const rpc of DEVNET_RPCS) {
            try {
                connection = new Connection(rpc, 'confirmed');
                await connection.getVersion();
                console.log(`\n🔗 Connected to Solana devnet via: ${rpc.split('?')[0].split('/').slice(0,3).join('/')}`);
                break;
            } catch (e) {
                console.log(`⚠️ RPC failed: ${rpc.split('?')[0]}`);
            }
        }
        if (!connection) {
            throw new Error("Failed to connect to any RPC endpoint");
        }
        
        // Create or load keypair
        const keypairPath = path.join(process.env.HOME || '/tmp', '.config', 'solana', 'entity-token.json');
        let payer;
        
        if (fs.existsSync(keypairPath)) {
            console.log("\n🔑 Loading existing keypair...");
            const secretKey = JSON.parse(fs.readFileSync(keypairPath, 'utf8'));
            payer = Keypair.fromSecretKey(new Uint8Array(secretKey));
        } else {
            console.log("\n🔑 Creating new keypair...");
            payer = Keypair.generate();
            
            // Save keypair
            fs.mkdirSync(path.dirname(keypairPath), { recursive: true });
            fs.writeFileSync(keypairPath, JSON.stringify(Array.from(payer.secretKey)));
            console.log(`Keypair saved to: ${keypairPath}`);
        }
        
        console.log(`📍 Authority: ${payer.publicKey.toString()}`);
        
        // Request airdrop
        console.log("\n💧 Requesting airdrop...");
        try {
            const signature = await connection.requestAirdrop(payer.publicKey, 2 * 1000000000); // 2 SOL
            await connection.confirmTransaction(signature);
            const balance = await connection.getBalance(payer.publicKey);
            console.log(`✅ Airdrop received. Balance: ${balance / 1000000000} SOL`);
        } catch (e) {
            console.log(`⚠️ Airdrop may have failed: ${e.message}`);
        }
        
        // Create token mint
        console.log("\n🪙 Creating $ENTITY token mint...");
        const mint = await createMint(
            connection,
            payer,
            payer.publicKey,
            payer.publicKey,
            DECIMALS
        );
        
        console.log(`✅ Token created: ${mint.toString()}`);
        
        // Create token account
        console.log("\n📦 Creating token account...");
        const tokenAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            payer,
            mint,
            payer.publicKey
        );
        console.log(`✅ Token account: ${tokenAccount.address.toString()}`);
        
        // Mint tokens
        console.log(`\n🏭 Minting ${TOTAL_SUPPLY} tokens...`);
        const mintAmount = TOTAL_SUPPLY * Math.pow(10, DECIMALS);
        await mintTo(
            connection,
            payer,
            mint,
            tokenAccount.address,
            payer,
            mintAmount
        );
        
        // Verify
        console.log("\n🔍 Verifying...");
        const mintInfo = await getMint(connection, mint);
        console.log(`Supply: ${Number(mintInfo.supply) / Math.pow(10, DECIMALS)}`);
        
        console.log("\n==============================================");
        console.log("✅ $ENTITY Token Deployed Successfully!");
        console.log("==============================================");
        console.log("\nToken Details:");
        console.log(`  Name: ${TOKEN_NAME}`);
        console.log(`  Symbol: ${TOKEN_SYMBOL}`);
        console.log(`  Mint Address: ${mint.toString()}`);
        console.log(`  Decimals: ${DECIMALS}`);
        console.log(`  Total Supply: ${TOTAL_SUPPLY}`);
        console.log(`  Authority: ${payer.publicKey.toString()}`);
        console.log(`  Network: devnet`);
        console.log("\nSolana Explorer:");
        console.log(`  https://explorer.solana.com/address/${mint.toString()}?cluster=devnet`);
        
        // Save deployment info
        const deploymentInfo = {
            name: TOKEN_NAME,
            symbol: TOKEN_SYMBOL,
            mint: mint.toString(),
            decimals: DECIMALS,
            totalSupply: TOTAL_SUPPLY,
            authority: payer.publicKey.toString(),
            network: 'devnet',
            tokenAccount: tokenAccount.address.toString(),
            deployedAt: new Date().toISOString(),
            explorer: `https://explorer.solana.com/address/${mint.toString()}?cluster=devnet`
        };
        
        const infoPath = path.join(process.cwd(), '$ENTITY_TOKEN_INFO.json');
        fs.writeFileSync(infoPath, JSON.stringify(deploymentInfo, null, 2));
        console.log(`\n💾 Deployment info saved to: ${infoPath}`);
        
    } catch (error) {
        console.error("\n❌ Deployment failed:", error.message);
        process.exit(1);
    }
}

deployEntityToken();
