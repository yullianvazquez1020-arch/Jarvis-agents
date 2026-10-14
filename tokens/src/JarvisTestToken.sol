// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title JarvisTestToken (JTT) — ERC-20 mínimo SOLO PARA TESTNET.
/// @notice Andamiaje técnico. Sin valor, sin venta, sin fondos reales. Lo legal/regulatorio es
///         responsabilidad del dueño (Yullian); este código no es asesoría legal.
contract JarvisTestToken {
    string public constant name = "Jarvis Test Token";
    string public constant symbol = "JTT";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    address public immutable owner;
    uint256 public constant MAX_SUPPLY = 1_000_000 ether;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error NotOwner();
    error MainnetBlocked(uint256 chainId);
    error CapExceeded();

    constructor() {
        // Defensa en profundidad: el contrato se niega a existir fuera de redes de prueba conocidas.
        if (!isTestnet(block.chainid)) revert MainnetBlocked(block.chainid);
        owner = msg.sender;
    }

    function isTestnet(uint256 id) public pure returns (bool) {
        return id == 31337 || id == 11155111 || id == 84532 || id == 80002; // anvil, Sepolia, Base Sepolia, Amoy
    }

    function mint(address to, uint256 value) external {
        if (msg.sender != owner) revert NotOwner();
        if (totalSupply + value > MAX_SUPPLY) revert CapExceeded();
        totalSupply += value;
        balanceOf[to] += value;
        emit Transfer(address(0), to, value);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _move(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= value, "allowance");
        if (a != type(uint256).max) allowance[from][msg.sender] = a - value;
        _move(from, to, value);
        return true;
    }

    function _move(address from, address to, uint256 value) internal {
        require(to != address(0), "zero");
        require(balanceOf[from] >= value, "balance");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }
}
