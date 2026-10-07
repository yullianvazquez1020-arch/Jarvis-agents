"""Offline female Spanish speech. Public model download, no inference API."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import wave

MODEL='es_ES-sharvard-medium.onnx'
BASE='https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/'
HASHES={MODEL:'40febfb1679c69a4505ff311dc136e121e3419a13a290ef264fdf43ddedd0fb1',MODEL+'.json':'7438c9b699c72b0c3388dae1b68d3f364dc66a2150fe554a1c11f03372957b2c'}

def model_dir():
    return Path(os.getenv('PIPER_MODEL_DIR',str(Path(__file__).parent/'piper_models')))

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def ensure_model(root):
    """Download only public, checksum-pinned files; cache across video jobs."""
    import httpx
    root.mkdir(parents=True,exist_ok=True)
    for name,expected in HASHES.items():
        target=root/name
        if target.exists() and digest(target)==expected:continue
        with tempfile.NamedTemporaryFile(dir=root,delete=False) as f:
            tmp=Path(f.name)
            try:
                with httpx.stream('GET',BASE+name,follow_redirects=True,timeout=60) as r:
                    r.raise_for_status();size=0
                    for block in r.iter_bytes():
                        size+=len(block)
                        if size>90*1024*1024:raise ValueError('Modelo de voz demasiado grande')
                        f.write(block)
                f.flush()
                if digest(tmp)!=expected:raise ValueError('Checksum del modelo de voz incorrecto')
                os.replace(tmp,target)
            finally:tmp.unlink(missing_ok=True)
    return root/MODEL

def synthesize(texts,destination,root):
    """One CPU thread, bounded text, isolated process freed before rendering."""
    if not isinstance(texts,list) or not 1<=len(texts)<=8 or any(not isinstance(t,str) or not t.strip() or len(t)>400 for t in texts):
        raise ValueError('Narración inválida')
    import onnxruntime as ort
    from piper import PiperVoice, SynthesisConfig
    from piper.config import PiperConfig
    model=ensure_model(root)
    config=PiperConfig.from_dict(json.loads(Path(str(model)+'.json').read_text()))
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.enable_cpu_mem_arena=False;options.enable_mem_pattern=False
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    voice=PiperVoice(session=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider']),config=config)
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=True)
    paths=[]
    for i,text in enumerate(texts):
        path=dest/f'{i}.wav'
        with wave.open(str(path),'wb') as wav:
            voice.synthesize_wav(text,wav,syn_config=SynthesisConfig(speaker_id=1,length_scale=1.08))
        with wave.open(str(path),'rb') as wav:
            seconds=wav.getnframes()/wav.getframerate()
            if not 0<seconds<=45:raise ValueError('Narración local demasiado larga')
        paths.append(str(path))
    return paths

async def local_narration(plan,temp):
    if plan.get('language','es')!='es':raise ValueError('La voz local instalada es en español; cambia el plan a es')
    texts=[s['narration'] for s in plan['scenes']]
    # No credentials are passed to the speech worker.
    env={k:v for k,v in os.environ.items() if k in ('PATH','LD_LIBRARY_PATH','PYTHONPATH','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','HTTP_PROXY','NO_PROXY')}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    proc=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).resolve()),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
    try:
        stdout,stderr=await asyncio.wait_for(proc.communicate(json.dumps({'texts':texts,'destination':str(temp),'models':str(model_dir())}).encode()),timeout=240)
    except BaseException:
        if proc.returncode is None:proc.kill()
        await proc.wait();raise
    if proc.returncode:
        logging.getLogger(__name__).warning('Local voice worker failed: exit=%s',proc.returncode)
        raise ValueError('No pude generar la voz local; no se usó ninguna API de pago')
    result=json.loads(stdout)
    logging.getLogger(__name__).warning('Local voice ready: scenes=%s peak_memory_mb=%s',len(result['paths']),result.get('peak_memory_mb'))
    return result['paths']

if __name__=='__main__':
    import resource
    request=json.loads(sys.stdin.read(16000))
    paths=synthesize(request['texts'],request['destination'],Path(request['models']))
    print(json.dumps({'paths':paths,'peak_memory_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)}))
