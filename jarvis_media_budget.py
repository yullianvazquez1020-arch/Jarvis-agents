"""Best-effort Linux container memory guard for isolated media workers.

The limit includes the server and its children. Sampling cannot guarantee that
a sudden allocation will never reach the container limit; keep inputs bounded.
"""
import asyncio
from pathlib import Path

MIB = 1024 * 1024


def memory_state():
    for used, limit in (
        ('/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory.max'),
        ('/sys/fs/cgroup/memory/memory.usage_in_bytes', '/sys/fs/cgroup/memory/memory.limit_in_bytes'),
    ):
        try:
            raw = Path(limit).read_text().strip()
            if raw == 'max':
                continue
            maximum = int(raw)
            current = int(Path(used).read_text().strip())
            if 0 <= current and 0 < maximum < 1 << 60:
                return current, maximum
        except (OSError, ValueError):
            continue
    return None


def check_start():
    state = memory_state()
    if state and state[1] - state[0] < 96 * MIB:
        raise ValueError('memoria insuficiente para iniciar el audio local; conserva la respuesta escrita')


async def communicate(proc, stdin, timeout):
    task = asyncio.create_task(proc.communicate(stdin))
    async def monitored():
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.1)
            if done:
                break
            state = memory_state()
            if state and state[0] >= state[1] - 64 * MIB:
                raise ValueError('audio local detenido por presión de memoria; conserva la respuesta escrita')
        return await task
    try:
        return await asyncio.wait_for(monitored(), timeout)
    except BaseException:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        # Drain pipes and reap the child before releasing the shared media lock.
        await asyncio.shield(task)
        await proc.wait()
        raise
