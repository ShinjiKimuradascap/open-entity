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
    console.log("\n[4/7] Deploying AgentToken...");
    const initialSupply = hre.ethers.utils.parseEther("10000000"); // 10M tokens
    const AgentToken = await hre.ethers.getContractFactory("AgentToken");
    const agentToken = await AgentToken.deploy(
        agentIdentity.address,
        reputationRegistry.address,
        initialSupply
    );
    await agentToken.deployed();
    console.log("AgentToken deployed to:", agentToken.address);
    
    // Deploy TaskEscrow
    console.log("\n[5/7] Deploying TaskEscrow...");
    const TaskEscrow = await hre.ethers.getContractFactory("TaskEscrow");
    const taskEscrow = await TaskEscrow.deploy(
        agentIdentity.address,
        agentToken.address
    );
    await taskEscrow.deployed();
    console.log("TaskEscrow deployed to:", taskEscrow.address);
    
    // Deploy ServiceRegistry
    console.log("\n[6/7] Deploying ServiceRegistry...");
    const ServiceRegistry = await hre.ethers.getContractFactory("ServiceRegistry");
    const serviceRegistry = await ServiceRegistry.deploy(
        agentIdentity.address,
        reputationRegistry.address
    );
    await serviceRegistry.deployed();
    console.log("ServiceRegistry deployed to:", serviceRegistry.address);
    
    // Deploy Governance
    console.log("\n[7/8] Deploying Governance...");
    const Governance = await hre.ethers.getContractFactory("Governance");
    const governance = await Governance.deploy(
        agentToken.address,
        taskEscrow.address
    );
    await governance.deployed();
    console.log("Governance deployed to:", governance.address);
    
    // Deploy OrderBook
    console.log("\n[8/8] Deploying OrderBook...");
    const OrderBook = await hre.ethers.getContractFactory("OrderBook");
    const orderBook = await OrderBook.deploy(
        serviceRegistry.address,
        agentToken.address,
        taskEscrow.address,
        agentIdentity.address
    );
    await orderBook.deployed();
    console.log("OrderBook deployed to:", orderBook.address);
    
    // Setup contract connections
    console.log("\n[Setup] Configuring contract connections...");
    
    // Grant VERIFIER_ROLE to OrderBook in ServiceRegistry
    await serviceRegistry.grantRole(
        hre.ethers.utils.keccak256(hre.ethers.utils.toUtf8Bytes("VERIFIER_ROLE")),
        orderBook.address
    );
    console.log("Granted VERIFIER_ROLE to OrderBook in ServiceRegistry");
    
    // Summary
    console.log("\n========================================");
    console.log("Deployment Summary");
    console.log("========================================");
    console.log("AgentIdentity:", agentIdentity.address);
    console.log("ReputationRegistry:", reputationRegistry.address);
    console.log("ValidationRegistry:", validationRegistry.address);
    console.log("AgentToken:", agentToken.address);
    console.log("TaskEscrow:", taskEscrow.address);
    console.log("ServiceRegistry:", serviceRegistry.address);
    console.log("Governance:", governance.address);
    console.log("OrderBook:", orderBook.address);
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
            AgentToken: agentToken.address,
            TaskEscrow: taskEscrow.address,
            ServiceRegistry: serviceRegistry.address,
            Governance: governance.address,
            OrderBook: orderBook.address
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
