// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {JarvisTestToken} from "../src/JarvisTestToken.sol";

/// Despliegue SOLO a testnet. La llave se pasa en la línea de comandos (--account/keystore), nunca en git.
/// Mainnet está DESHABILITADA: MAINNET_ENABLED es una constante false; activarla exige un cambio de código
/// revisado y aprobado explícitamente por el dueño en un PR, y aun así el contrato rechaza mainnet.
contract Deploy is Script {
    bool internal constant MAINNET_ENABLED = false;

    function run() external returns (JarvisTestToken token) {
        bool testnet = block.chainid == 31337 || block.chainid == 11155111 || block.chainid == 84532 || block.chainid == 80002;
        require(testnet || MAINNET_ENABLED, "mainnet deshabilitada: requiere aprobacion explicita del dueno");
        vm.startBroadcast();
        token = new JarvisTestToken();
        vm.stopBroadcast();
    }
}
