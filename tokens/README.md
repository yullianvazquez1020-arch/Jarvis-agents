# Tokens (cripto) — andamiaje técnico SOLO TESTNET

**Legal y regulatorio: responsabilidad exclusiva de Yullian.** Este repositorio no da asesoría legal,
fiscal ni de valores. Antes de cualquier uso fuera de testnet, consulta a un abogado/CPA.

- `src/JarvisTestToken.sol`: ERC-20 mínimo (JTT), tope 1,000,000, `mint` solo del owner.
  El constructor revierte fuera de anvil (31337), Sepolia (11155111), Base Sepolia (84532) y Amoy (80002).
- `test/JarvisTestToken.t.sol`: pruebas Foundry (mint, allowance, tope, mainnet bloqueada).
- `script/Deploy.s.sol`: despliegue solo testnet; `MAINNET_ENABLED = false`.
- Sin llaves privadas en git (`.gitignore` excluye `.env`, `*.key`, `keystore/`). Sin fondos reales.
- **No se ha desplegado nada.**

Correr pruebas (local): `cd tokens && forge install foundry-rs/forge-std --no-git && forge test`
Las guardas también se verifican en `tests/test_frentes_tokens.py` (sin red).
