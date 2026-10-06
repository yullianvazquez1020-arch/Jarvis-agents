"""Small original educational animatic renderer. Uses geometric art, no stock footage.
Produces review MP4, not a promise of production quality or monetization.
"""
import math, os, re, shutil, subprocess, tempfile, textwrap, time, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def _ffmpeg():
    path=shutil.which('ffmpeg')
    if path:return path
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'):
        if Path(path).exists():return ImageFont.truetype(path,size)
    return ImageFont.load_default(size=size)

def _duration(path,ffmpeg):
    r=subprocess.run([ffmpeg,'-hide_banner','-i',str(path)],capture_output=True,text=True,timeout=30)
    m=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',r.stderr)
    if not m:raise ValueError('No pude medir la narración')
    return int(m[1])*3600+int(m[2])*60+float(m[3])

def frame(scene,title,index,total,t,width=960,height=540):
    im=Image.new('RGB',(width,height),'#FAF7ED');d=ImageDraw.Draw(im)
    d.rounded_rectangle((24,20,width-24,96),22,fill='#173A56')
    title=title[:55]
    d.text((width//2,58),title,font=font(28),fill='white',anchor='mm')
    # An original little geometric guide waves beside the exercise.
    bob=math.sin(t*2)*5
    d.ellipse((30,170+bob,130,270+bob),fill='#F9C74F');d.ellipse((58,200+bob,67,213+bob),fill='#173A56');d.ellipse((94,200+bob,103,213+bob),fill='#173A56');d.arc((60,209+bob,103,243+bob),0,180,fill='#173A56',width=4)
    count=scene['count'];visible=min(count,1+int(t/.8));size=min(85,340/max(count,1));gap=12;totalwidth=count*size+(count-1)*gap;start=540-totalwidth/2
    for k in range(visible):
        x=start+k*(size+gap);y=210+math.sin(t*1.6+k)*7;color=scene['color'];box=(x,y,x+size,y+size)
        if scene['shape']=='circle':d.ellipse(box,fill=color,outline='#173A56',width=3)
        elif scene['shape']=='square':d.rounded_rectangle(box,10,fill=color,outline='#173A56',width=3)
        elif scene['shape']=='triangle':d.polygon([(x+size/2,y),(x+size,y+size),(x,y+size)],fill=color,outline='#173A56')
        else:
            points=[]
            for n in range(10):
                a=-math.pi/2+n*math.pi/5;r=size*(.5 if n%2==0 else .23);points.append((x+size/2+r*math.cos(a),y+size/2+r*math.sin(a)))
            d.polygon(points,fill=color,outline='#173A56')
    lines=textwrap.wrap(scene['text'],width=39)
    for n,line in enumerate(lines[:3]):d.text((width//2,376+n*37),line,font=font(31),fill='#173A56',anchor='mm')
    d.rounded_rectangle((34,500,width-34,515),7,fill='#DDE9E8');length=(width-68)*(index+min(t/scene['duration'],1))/total
    d.rounded_rectangle((34,500,34+max(8,length),515),7,fill='#25A89C')
    return im

def render_video(plan,output,audio_paths=None):
    ffmpeg=_ffmpeg();audio_paths=audio_paths or [];scenes=[dict(s) for s in plan['scenes']]
    if audio_paths and len(audio_paths)!=len(scenes):raise ValueError('Falta narración de una escena')
    for i,s in enumerate(scenes):
        duration=max(float(s['seconds']),_duration(audio_paths[i],ffmpeg)+.6 if audio_paths else 0)
        if duration>45:raise ValueError('Narración demasiado larga; acorta la escena')
        s['duration']=duration
    if sum(s['duration'] for s in scenes)>240:raise ValueError('Máximo 4 minutos por previsualización')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);fps=12;start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='jarvis-render-') as tmp:
        video=Path(tmp)/'picture.mp4';err=Path(tmp)/'ffmpeg.log'
        args=[ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','960x540','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
        with err.open('wb') as errors:
            proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
            try:
                for i,s in enumerate(scenes):
                    frames=math.ceil(s['duration']*fps);s['duration']=frames/fps
                    for f in range(frames):
                        if time.monotonic()-start>240:raise TimeoutError('Render agotó tiempo disponible')
                        proc.stdin.write(frame(s,plan['title'],i,len(scenes),f/fps).tobytes())
                proc.stdin.close();code=proc.wait(timeout=60)
                if code:raise ValueError('Falló el codificador de video')
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
        destination=Path(tmp)/'final.mp4'
        if audio_paths:
            joined=Path(tmp)/'narration.wav'
            with wave.open(str(joined),'wb') as dest:
                dest.setparams((1,2,44100,0,'NONE','not compressed'))
                for i,s in enumerate(scenes):
                    part=Path(tmp)/f'audio-{i}.wav'
                    result=subprocess.run([ffmpeg,'-y','-v','error','-i',audio_paths[i],'-af','apad','-t',str(s['duration']),'-ar','44100','-ac','1','-c:a','pcm_s16le',str(part)],capture_output=True,timeout=60)
                    if result.returncode:raise ValueError('No pude preparar narración')
                    with wave.open(str(part),'rb') as src:dest.writeframes(src.readframes(src.getnframes()))
            result=subprocess.run([ffmpeg,'-y','-v','error','-i',str(video),'-i',str(joined),'-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(destination)],capture_output=True,timeout=90)
            if result.returncode:raise ValueError('No pude unir narración')
        else:shutil.copyfile(video,destination)
        shutil.copyfile(destination,output)
    return {'seconds':sum(s['duration'] for s in scenes),'narration':bool(audio_paths),'path':str(output)}
