"""Portable private data in backups; key material is always kept separately."""
import json
import os

KEYS = {name: 'jarvis:' + name for name in ('history', 'profile', 'bio', 'diary')}


def export(core):
    seal = core._seal_module()
    values = {}
    for name, key in KEYS.items():
        raw = core._kv_raw(key, None)
        # Preserve ciphertext even when the key is unavailable: never export a silent default.
        if raw is not None and not (isinstance(raw, str) and raw.startswith('sealed:')):
            if seal is not None and seal.key_state() == 'invalid':
                raise ValueError('Clave de cifrado inválida; no exporto datos privados en claro')
            if seal is not None and seal.key_state() == 'ok':
                raw = seal.seal(raw)
        values[name] = raw
    return {'format': 1, 'values': values}


def restore_values(core, section):
    if not isinstance(section, dict) or section.get('format') != 1:
        raise ValueError('Formato de respaldo privado inválido')
    values = section.get('values')
    if not isinstance(values, dict) or set(values) != set(KEYS):
        raise ValueError('El respaldo privado debe incluir historial, perfil, bio y diario')
    seal = core._seal_module()
    writes = {}
    for name, key in KEYS.items():
        value = values[name]
        if isinstance(value, str) and value.startswith('sealed:'):
            if seal is None or seal.key_state() != 'ok':
                raise ValueError('Se requiere la clave original para recuperar el respaldo privado')
            try:
                value = seal.open_seal(value)
            except Exception:
                raise ValueError('El respaldo privado no abre con esta clave o está dañado') from None
        if value is not None:
            if name == 'history' and (not isinstance(value, list) or not all(isinstance(r, dict) for r in value)):
                raise ValueError('Historial del respaldo inválido')
            if name == 'profile' and not isinstance(value, dict):
                raise ValueError('Perfil del respaldo inválido')
            # No executable objects; reject NaN/Infinity before any write.
            json.dumps(value, allow_nan=False)
            writes[key] = value
        # Empty sections do not erase newer data at the destination.
    return writes


def boot_migrate(core):
    """Explicit operator opt-in bound to the expected key fingerprint, never forced."""
    expected = os.getenv('SEAL_MIGRATE_KEY_FINGERPRINT', '').strip()
    if not expected:
        return
    seal = core._seal_module()
    if seal is None or seal.fingerprint() != expected:
        raise RuntimeError('La clave no coincide con la migración autorizada')
    result = core.seal_migrate(apply=True)
    if not result.get('ok'):
        raise RuntimeError('La migración de cifrado no se pudo verificar; revisa /cifrado')
    # Decode the exported representation and compare against storage, without restoring live data.
    snapshot = core.snapshot()
    recovered = restore_values(core, snapshot['private_data'])
    for key, value in recovered.items():
        if core._seal_canon(value) != core._seal_canon(core.kv_get(key, None)):
            raise RuntimeError('El respaldo privado no coincide con los datos guardados')
    saved = core.daily_backup()
    if core.USE_REDIS:
        stored = core._redis(['GET', 'jarvis:backup:' + core._today().isoformat()])
        if not stored or restore_values(core, json.loads(stored)['private_data']) != recovered:
            raise RuntimeError('No se pudo verificar el respaldo persistente')
    states = {row['key']: row.get('after') for row in result['rows']}
    core.logger.info('Private backup verified: fingerprint=%s states=%s daily_saved=%s',
                     expected, states, saved)
