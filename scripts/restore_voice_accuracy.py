#!/usr/bin/env python3
"""Undo the provisional tiny-model trial when the owner reports recognition errors."""
from pathlib import Path
import sys
import mac_voice_benchmark as bench


def main():
    home = Path.home()
    repo = bench.active_repo(home)
    path, original, cfg = bench.config(home, repo)
    current = Path(cfg.get('VOICE_STT_MODEL_PATH', ''))
    if current.name != 'ggml-tiny-q5_1.bin':
        print('No provisional Tiny model selected; voice configuration preserved.')
        return 0
    base = current.with_name('ggml-base.bin')
    if not base.is_file():
        print('Previous base model missing; no configuration changed.')
        return 1
    # Preserve other engine preferences; rollback and backup handled by existing installer helper.
    result = bench.apply_choice(path, original, {
        'model': str(base), 'threads': 2,
        'fast': cfg.get('VOICE_STT_FAST', 'true').lower() in ('true', '1', 'yes')
    }, repo)
    print('Recognition model restored; real voice accuracy and latency still need measurement.' if result['applied']
          else 'Could not apply recognition restoration; previous configuration restored.')
    return 0 if result['applied'] else 1

if __name__ == '__main__':
    sys.exit(main())
