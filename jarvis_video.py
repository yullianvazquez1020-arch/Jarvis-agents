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

def _animal(d,kind,x,y,size,t):
    """Original vector characters; no downloaded or licensed character assets."""
    def box(a,b,c,e): return (x+a*size,y+b*size,x+c*size,y+e*size)
    ink='#173A56'
    if kind=='coqui':
        for side in (0, .65):
            d.ellipse(box(side,.58,side+.35,.96),fill='#36A85C',outline=ink,width=2)
        d.ellipse(box(.15,.22,.85,.87),fill='#58C77E',outline=ink,width=3)
        for side in (.2,.6):
            d.ellipse(box(side,.08,side+.22,.35),fill='#58C77E',outline=ink,width=2)
            d.ellipse(box(side+.05,.13,side+.17,.28),fill='white')
            d.ellipse(box(side+.09,.16,side+.14,.25),fill=ink)
        d.arc(box(.32,.42,.69,.66),0,180,fill=ink,width=3)
    elif kind=='crab':
        for k in range(3):
            d.line([(x+.25*size,y+(.5+k*.1)*size),(x+.04*size,y+(.59+k*.12)*size)],fill=ink,width=4)
            d.line([(x+.75*size,y+(.5+k*.1)*size),(x+.96*size,y+(.59+k*.12)*size)],fill=ink,width=4)
        d.ellipse(box(.17,.32,.83,.85),fill='#F27855',outline=ink,width=3)
        for side in (.3,.61):
            d.line([(x+(side+.04)*size,y+.4*size),(x+(side+.04)*size,y+.22*size)],fill=ink,width=4)
            d.ellipse(box(side,.1,side+.14,.26),fill='white',outline=ink,width=2)
            d.ellipse(box(side+.05,.14,side+.09,.23),fill=ink)
        for side in (0,.77):
            d.ellipse(box(side,.14,side+.23,.42),fill='#F27855',outline=ink,width=2)
        d.arc(box(.35,.49,.65,.69),0,180,fill=ink,width=3)
    else:
        d.polygon([(x+.7*size,y+.56*size),(x+1.14*size,y+.76*size),(x+.74*size,y+.79*size)],fill='#65BA75',outline=ink)
        for k in range(6):
            d.polygon([(x+(.24+k*.09)*size,y+.38*size),(x+(.27+k*.09)*size,y+.2*size),(x+(.31+k*.09)*size,y+.4*size)],fill='#2F8253')
        d.ellipse(box(.19,.35,.92,.84),fill='#72C98D',outline=ink,width=3)
        d.ellipse(box(.07,.23,.43,.63),fill='#72C98D',outline=ink,width=3)
        d.ellipse(box(.17,.3,.26,.41),fill='white');d.ellipse(box(.2,.32,.24,.4),fill=ink)
        for side in (.34,.72): d.ellipse(box(side,.68,side+.17,.96),fill='#4EAA71',outline=ink,width=2)
        d.arc(box(.1,.39,.32,.53),0,160,fill=ink,width=2)

def frame(scene,title,index,total,t,width=960,height=540):
    im=Image.new('RGB',(width,height),'#D9F3FA');d=ImageDraw.Draw(im)
    # Tropical landscape with parallax clouds and layered hills.
    d.ellipse((815,100,890,175),fill='#FFD56D')
    for k in range(3):
        cx=(k*360+t*7)%1150-100
        d.ellipse((cx,115,cx+110,150),fill='white');d.ellipse((cx+25,96,cx+80,150),fill='white')
    d.polygon([(0,310),(160,220),(340,310),(540,210),(780,305),(960,245),(960,540),(0,540)],fill='#A2DCC0')
    d.ellipse((-180,305,600,640),fill='#62BC91');d.ellipse((420,305,1180,650),fill='#7EC99B')
    d.rounded_rectangle((22,18,width-22,91),20,fill='#173A56')
    d.text((width//2,54),title[:55],font=font(27),fill='white',anchor='mm')
    # Leaf clusters frame the lesson without covering captions.
    for x in (24,895):
        d.line((x+20,200,x+20,345),fill='#388460',width=7)
        for k in range(3): d.ellipse((x-8,195+k*35,x+44,223+k*35),fill='#3B9B6B')
    count=scene['count'];visible=min(count,1+int(t/.9));size=min(130,520/max(count,1));gap=18
    totalwidth=count*size+(count-1)*gap;start=width/2-totalwidth/2
    for k in range(visible):
        x=start+k*(size+gap);y=215+math.sin(t*2+k)*6
        d.ellipse((x+8,335,x+size+12,352),fill='#51A780')
        character=scene.get('character','shapes')
        if character in ('coqui','crab','iguana'):_animal(d,character,x,y,size,t)
        elif character=='friends':_animal(d,('coqui','crab','iguana')[k%3],x,y,size,t)
        else:
            box=(x,y,x+size,y+size);color=scene['color']
            if scene['shape']=='circle': d.ellipse(box,fill=color,outline='#173A56',width=3)
            elif scene['shape']=='square': d.rounded_rectangle(box,12,fill=color,outline='#173A56',width=3)
            elif scene['shape']=='triangle': d.polygon([(x+size/2,y),(x+size,y+size),(x,y+size)],fill=color,outline='#173A56')
            else:
                points=[]
                for n in range(10):
                    a=-math.pi/2+n*math.pi/5;r=size*(.5 if n%2==0 else .23);points.append((x+size/2+r*math.cos(a),y+size/2+r*math.sin(a)))
                d.polygon(points,fill=color,outline='#173A56')
        d.text((x+size/2,365),str(k+1),font=font(22),fill='#173A56',anchor='mm')
    d.rounded_rectangle((75,389,width-75,480),19,fill='#FFFDF4')
    for n,line in enumerate(textwrap.wrap(scene['text'],width=43)[:2]):
        d.text((width//2,414+n*33),line,font=font(29),fill='#173A56',anchor='mm')
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
