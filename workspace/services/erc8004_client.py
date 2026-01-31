"""
ERC-8004 Identity Registry Client

Web3.py based client for interacting with AgentIdentity smart contract.
Provides Python interface for agent registration and management on Ethereum.
"""

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.types import TxReceipt, Wei


@dataclass
class AgentData:
    """Agent metadata structure matching Solidity struct"""
    name: str
    endpoint: str
    public_key: str
    registered_at: int
    active: bool
    
    @classmethod
    def from_contract(cls, data: tuple) -> "AgentData":
        """Convert contract tuple response to AgentData"""
        return cls(
            name=data[0],
            endpoint=data[1],
            public_key=data[2],
            registered_at=data[3],
            active=data[4]
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "registered_at": self.registered_at,
            "active": self.active
        }


# Contract ABI for AgentIdentity
CONTRACT_ABI = [
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "name", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "endpoint", "type": "string"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"}
        ],
        "name": "AgentRegistered",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "name", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "endpoint", "type": "string"}
        ],
        "name": "AgentUpdated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "AgentDeactivated",
        "type": "event"
    },
    # Read functions
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "getAgent",
        "outputs": [{
            "components": [
                {"internalType": "string", "name": "name", "type": "string"},
                {"internalType": "string", "name": "endpoint", "type": "string"},
                {"internalType": "string", "name": "publicKey", "type": "string"},
                {"internalType": "uint256", "name": "registeredAt", "type": "uint256"},
                {"internalType": "bool", "name": "active", "type": "bool"}
            ],
            "internalType": "struct AgentIdentity.Agent",
            "name": "",
            "type": "tuple"
        }],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "endpoint", "type": "string"}],
        "name": "getTokenIdByEndpoint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "isActive",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalAgents",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "getAgentsByOwner",
        "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    # Write functions
    {
        "inputs": [
            {"internalType": "string", "name": "name", "type": "string"},
            {"internalType": "string", "name": "endpoint", "type": "string"},
            {"internalType": "string", "name": "publicKey", "type": "string"}
        ],
        "name": "registerAgent",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "string", "name": "name", "type": "string"},
            {"internalType": "string", "name": "endpoint", "type": "string"}
        ],
        "name": "updateAgent",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "string", "name": "publicKey", "type": "string"}
        ],
        "name": "updatePublicKey",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "deactivateAgent",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


class ERC8004Client:
    """
    ERC-8004 Identity Registry Client
    
    Provides interface to interact with AgentIdentity smart contract
    for AI agent registration and management.
    """
    
    def __init__(
        self,
        contract_address: Optional[str] = None,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None
    ):
        """
        Initialize ERC8004 client
        
        Args:
            contract_address: Deployed contract address (or CONTRACT_ADDRESS env var)
            rpc_url: Ethereum RPC endpoint (or RPC_URL env var)
            private_key: Private key for signing transactions (or PRIVATE_KEY env var)
        """
        self.contract_address = contract_address or os.getenv("CONTRACT_ADDRESS")
        self.rpc_url = rpc_url or os.getenv("RPC_URL")
        self.private_key = private_key or os.getenv("PRIVATE_KEY")
        
        if not self.contract_address:
            raise ValueError("Contract address required. Set CONTRACT_ADDRESS env var or pass to constructor.")
        if not self.rpc_url:
            raise ValueError("RPC URL required. Set RPC_URL env var or pass to constructor.")
        if not self.private_key:
            raise ValueError("Private key required. Set PRIVATE_KEY env var or pass to constructor.")
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC at {self.rpc_url}")
        
        # Setup account
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address
        
        # Initialize contract
        self.contract: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_address),
            abi=CONTRACT_ABI
        )
    
    def _send_transaction(self, function_name: str, *args, **kwargs) -> TxReceipt:
        """
        Send a transaction to the contract
        
        Args:
            function_name: Name of the contract function to call
            *args: Positional arguments for the function
            **kwargs: Transaction parameters (gas, gas_price, etc.)
        
        Returns:
            Transaction receipt
        """
        # Build transaction
        contract_function = getattr(self.contract.functions, function_name)
        tx = contract_function(*args).build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': kwargs.get('gas', 200000),
            'gasPrice': kwargs.get('gas_price', self.w3.eth.gas_price),
            'chainId': self.w3.eth.chain_id
        })
        
        # Sign and send
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for receipt
        return self.w3.eth.wait_for_transaction_receipt(tx_hash)
    
    def _call_view_function(self, function_name: str, *args) -> Any:
        """Call a view/pure function"""
        contract_function = getattr(self.contract.functions, function_name)
        return contract_function(*args).call()
    
    def register_agent(
        self,
        name: str,
        endpoint: str,
        public_key: str,
        **tx_kwargs
    ) -> int:
        """
        Register a new agent identity
        
        Args:
            name: Agent name
            endpoint: Agent's API endpoint URL
            public_key: Agent's public key for signature verification
            **tx_kwargs: Transaction parameters
        
        Returns:
            token_id: The newly minted token ID
        
        Raises:
            ValueError: If parameters are invalid
            ContractLogicError: If endpoint already registered
        """
        if not name or not name.strip():
            raise ValueError("Name cannot be empty")
        if not endpoint or not endpoint.strip():
            raise ValueError("Endpoint cannot be empty")
        if not public_key or not public_key.strip():
            raise ValueError("Public key cannot be empty")
        
        receipt = self._send_transaction(
            'registerAgent',
            name,
            endpoint,
            public_key,
            **tx_kwargs
        )
        
        # Extract tokenId from event logs
        for log in receipt['logs']:
            try:
                event = self.contract.events.AgentRegistered().process_receipt({'logs': [log]})[0]
                return event['args']['tokenId']
            except (IndexError, KeyError, Exception):
                continue
        
        # Fallback: get from transaction receipt status
        # In production, you'd want to query the contract for the tokenId
        raise RuntimeError("Failed to extract tokenId from transaction receipt")
    
    def get_agent(self, token_id: int) -> AgentData:
        """
        Get agent metadata by tokenId
        
        Args:
            token_id: The token ID to look up
        
        Returns:
            AgentData containing all metadata
        
        Raises:
            ContractLogicError: If agent does not exist
        """
        result = self._call_view_function('getAgent', token_id)
        return AgentData.from_contract(result)
    
    def get_token_id_by_endpoint(self, endpoint: str) -> Optional[int]:
        """
        Get tokenId by endpoint
        
        Args:
            endpoint: The endpoint URL to look up
        
        Returns:
            token_id if found, None otherwise (returns 0 from contract if not found)
        """
        token_id = self._call_view_function('getTokenIdByEndpoint', endpoint)
        return token_id if token_id > 0 else None
    
    def update_agent(
        self,
        token_id: int,
        **kwargs
    ) -> TxReceipt:
        """
        Update agent metadata
        
        Args:
            token_id: The token ID to update
            **kwargs: Fields to update (name, endpoint, public_key)
        
        Returns:
            Transaction receipt
        
        Note:
            At least one of name or endpoint must be provided
        """
        name = kwargs.get('name')
        endpoint = kwargs.get('endpoint')
        public_key = kwargs.get('public_key')
        
        # Update name and/or endpoint
        if name or endpoint:
            # Get current values if not provided
            current = self.get_agent(token_id)
            name = name or current.name
            endpoint = endpoint or current.endpoint
            
            receipt = self._send_transaction(
                'updateAgent',
                token_id,
                name,
                endpoint,
                **{k: v for k, v in kwargs.items() if k not in ('name', 'endpoint', 'public_key')}
            )
        
        # Update public key if provided
        if public_key:
            receipt = self._send_transaction(
                'updatePublicKey',
                token_id,
                public_key,
                **{k: v for k, v in kwargs.items() if k not in ('name', 'endpoint', 'public_key')}
            )
        
        return receipt
    
    def deactivate_agent(self, token_id: int, **tx_kwargs) -> TxReceipt:
        """
        Deactivate agent identity
        
        Args:
            token_id: The token ID to deactivate
            **tx_kwargs: Transaction parameters
        
        Returns:
            Transaction receipt
        """
        return self._send_transaction('deactivateAgent', token_id, **tx_kwargs)
    
    def is_active(self, token_id: int) -> bool:
        """
        Check if agent is active
        
        Args:
            token_id: The token ID to check
        
        Returns:
            True if agent is active
        """
        return self._call_view_function('isActive', token_id)
    
    def total_agents(self) -> int:
        """
        Get total number of registered agents
        
        Returns:
            Total count of agents
        """
        return self._call_view_function('totalAgents')
    
    def get_agents_by_owner(self, owner_address: Optional[str] = None) -> List[int]:
        """
        Get all token IDs owned by an address
        
        Args:
            owner_address: Address to query (default: connected account)
        
        Returns:
            List of token IDs
        """
        owner = owner_address or self.address
        return list(self._call_view_function('getAgentsByOwner', owner))
    
    def owner_of(self, token_id: int) -> ChecksumAddress:
        """
        Get owner address of a token
        
        Args:
            token_id: The token ID
        
        Returns:
            Owner's address
        """
        return self._call_view_function('ownerOf', token_id)
    
    def balance_of(self, owner_address: Optional[str] = None) -> int:
        """
        Get number of tokens owned by an address
        
        Args:
            owner_address: Address to query (default: connected account)
        
        Returns:
            Token balance
        """
        owner = owner_address or self.address
        return self._call_view_function('balanceOf', owner)


# Convenience functions for direct use
def get_client(
    contract_address: Optional[str] = None,
    rpc_url: Optional[str] = None,
    private_key: Optional[str] = None
) -> ERC8004Client:
    """
    Get configured ERC8004Client instance
    
    Uses environment variables if parameters not provided:
    - CONTRACT_ADDRESS: Deployed contract address
    - RPC_URL: Ethereum RPC endpoint
    - PRIVATE_KEY: Private key for signing
    """
    return ERC8004Client(
        contract_address=contract_address,
        rpc_url=rpc_url,
        private_key=private_key
    )


if __name__ == "__main__":
    # Example usage
    import json
    
    # Check environment
    if not os.getenv("CONTRACT_ADDRESS"):
        print("Set CONTRACT_ADDRESS environment variable")
        exit(1)
    
    client = get_client()
    print(f"Connected to: {client.rpc_url}")
    print(f"Account: {client.address}")
    print(f"Contract: {client.contract_address}")
    print(f"Total agents: {client.total_agents()}")
