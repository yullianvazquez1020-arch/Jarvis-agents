"""Strict validation of the WAV the panel sends (PCM 16-bit, mono, 16 kHz). Python 3.8+, no dependencies."""
import struct

RATE = 16000
MAX_SECONDS = 60
MAX_BYTES = 44 + RATE * 2 * MAX_SECONDS


class AudioError(ValueError):
    pass


def check_wav(data):
    """-> duration in seconds. Raises AudioError before anything decodes untrusted audio."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 44:
        raise AudioError("audio vacío o incompleto")
    if len(data) > MAX_BYTES:
        raise AudioError(f"audio de más de {MAX_SECONDS} segundos")
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioError("no es un archivo WAV")
    pos, fmt, size = 12, None, None
    while pos + 8 <= len(data):
        cid, clen = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if cid == b"fmt " and clen >= 16:
            fmt = struct.unpack("<HHIIHH", data[body:body + 16])
        elif cid == b"data":
            size = min(clen, len(data) - body)
            break
        pos = body + clen + (clen & 1)
    if not fmt or size is None:
        raise AudioError("WAV sin formato o sin datos")
    audio_format, channels, rate, _, _, bits = fmt
    if (audio_format, channels, rate, bits) != (1, 1, RATE, 16):
        raise AudioError("se espera WAV PCM de 16 bits, mono, 16 kHz")
    seconds = size / (RATE * 2)
    if seconds < 0.2:
        raise AudioError("audio demasiado corto")
    return round(seconds, 2)


def make_wav(samples):
    """samples: iterable of ints (-32768..32767). Used by tests and the voice check."""
    pcm = b"".join(struct.pack("<h", max(-32768, min(32767, int(s)))) for s in samples)
    header = (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " +
              struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)))
    return header + pcm
