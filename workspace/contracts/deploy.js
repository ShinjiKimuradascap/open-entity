// Hardhat deployment script for AI Collaboration Platform contracts
const hre = require("hardhat");

async function main() {
    const [deployer] = await hre.ethers.getSigners();
    console.log("Deploying contracts with account:", deployer.address);
    
    // Deploy AgentIdentity
    console.log("\n[1/4] Deploying AgentIdentity...");
    const AgentIdentity = await hre.ethers.getContractFactory("AgentIdentity");
    const agentIdentity = await AgentIdentity.deploy();
    await agentIdentity.deployed();
    console.log("AgentIdentity deployed to:", agentIdentity.address);
    
    // Deploy ReputationRegistry
    console.log("\n[2/4] Deploying ReputationRegistry...");
    const ReputationRegistry = await hre.ethers.getContractFactory("ReputationRegistry");
    const reputationRegistry = await ReputationRegistry.deploy(agentIdentity.address);
    await reputationRegistry.deployed();
    console.log("ReputationRegistry deployed to:", reputationRegistry.address);
    
    // Deploy ValidationRegistry
    console.log("\n[3/4] Deploying ValidationRegistry...");
    const ValidationRegistry = await hre.ethers.getContractFactory("ValidationRegistry");
    const validationRegistry = await ValidationRegistry.deploy(
        agentIdentity.address,
        reputationRegistry.address
    );
    await validationRegistry.deployed();
    console.log("ValidationRegistry deployed to:", validationRegistry.address);
    
    // Deploy AgentToken
    console.log("\n[4/4] Deploying AgentToken...");
    const initialSupply = hre.ethers.utils.parseEther("10000000"); // 10M tokens
    const AgentToken = await hre.ethers.getContractFactory("AgentToken");
    const agentToken = await AgentToken.deploy(
        agentIdentity.address,
        reputationRegistry.address,
        initialSupply
    );
    await agentToken.deployed();
    console.log("AgentToken deployed to:", agentToken.address);
    
    // Summary
    console.log("\n========================================");
    console.log("Deployment Summary");
    console.log("========================================");
    console.log("AgentIdentity:", agentIdentity.address);
    console.log("ReputationRegistry:", reputationRegistry.address);
    console.log("ValidationRegistry:", validationRegistry.address);
    console.log("AgentToken:", agentToken.address);
    console.log("========================================");
    
    // Save deployment info
    const deploymentInfo = {
        network: hre.network.name,
        chainId: hre.network.config.chainId,
        deployer: deployer.address,
        contracts: {
            AgentIdentity: agentIdentity.address,
            ReputationRegistry: reputationRegistry.address,
            ValidationRegistry: validationRegistry.address,
            AgentToken: agentToken.address
        },
        timestamp: new Date().toISOString()
    };
    
    const fs = require("fs");
    fs.writeFileSync(
        `deployment-${hre.network.name}.json`,
        JSON.stringify(deploymentInfo, null, 2)
    );
    console.log("\nDeployment info saved to:", `deployment-${hre.network.name}.json`);
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
