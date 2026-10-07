"""Small original educational animatic renderer. Uses geometric art, no stock footage.
Produces review MP4, not a promise of production quality or monetization.
"""
import math, os, re, shutil, subprocess, tempfile, textwrap, time, wave
from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

def _ffmpeg():
    path=shutil.which('ffmpeg')
    if path:return path
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

@lru_cache(maxsize=32)
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
    """Hand-drawn original characters with independent facial and limb motion."""
    def box(a,b,c,e):return (x+a*size,y+b*size,x+c*size,y+e*size)
    def ellipse(a,b,c,e,color,outline=None):d.ellipse(box(a,b,c,e),fill=color,outline=outline,width=max(2,int(size*.018)))
    ink='#243D50';blink=t%3.6>3.42;step=math.sin(t*7)
    def eye(a,b,w=.16):
        if blink:d.arc(box(a,b,a+w,b+.09),0,180,fill=ink,width=3)
        else:
            ellipse(a,b,a+w,b+.2,'#FFFEF5',ink)
            ellipse(a+w*.35,b+.04,a+w*.75,b+.16,ink)
            ellipse(a+w*.4,b+.045,a+w*.53,b+.075,'white')
    if kind=='coqui':
        # Splayed toes, warm belly, cheek blush and a waving foreleg.
        for side in (.04,.69):
            ellipse(side,.64,side+.28,.92,'#33A875',ink)
            for n in range(3):ellipse(side+n*.065,.85,side+.11+n*.065,.97,'#43BE83',ink)
        ellipse(.19,.29,.81,.88,'#54C88E',ink)
        ellipse(.3,.56,.7,.82,'#BDEDA0')
        ellipse(.12,.2,.88,.65,'#68D99B',ink)
        for side in (.2,.61):
            ellipse(side-.045,.085,side+.23,.37,'#68D99B',ink);eye(side,.12)
        ellipse(.19,.46,.31,.52,'#F2B5A6');ellipse(.69,.46,.81,.52,'#F2B5A6')
        d.arc(box(.33,.4,.67,.58),0,180,fill=ink,width=3)
        d.line((x+.74*size,y+.61*size,x+.94*size,y+(.45+.09*math.sin(t*5))*size),fill=ink,width=5)
        ellipse(.87,.38+.09*math.sin(t*5),.98,.5+.09*math.sin(t*5),'#68D99B',ink)
    elif kind=='crab':
        for k in range(3):
            h=(.62+k*.09);swing=.035*math.sin(t*8+k)
            for side,direction in ((.25,-1),(.75,1)):
                d.line([(x+side*size,y+h*size),(x+(side+direction*.15)*size,y+(h+.06+swing)*size),(x+(side+direction*.22)*size,y+(h+.13)*size)],fill=ink,width=4)
        ellipse(.15,.34,.85,.85,'#E45A39',ink);ellipse(.18,.34,.82,.75,'#FF9C59')
        ellipse(.3,.58,.7,.79,'#FFD593')
        for side in (.3,.56):
            d.line((x+(side+.07)*size,y+.43*size,x+(side+.07)*size,y+.2*size),fill=ink,width=4);eye(side,.12)
        for side in (.0,.79):
            h=.19+.05*step
            ellipse(side,h,side+.22,h+.29,'#FF8C55',ink)
            d.polygon([(x+(side+.1)*size,y+h*size),(x+(side+.16)*size,y+(h+.12)*size),(x+(side+.2)*size,y+h*size)],fill='#E5F5EF')
        ellipse(.23,.5,.32,.55,'#F66A61');ellipse(.68,.5,.77,.55,'#F66A61')
        d.arc(box(.36,.55,.64,.7),0,180,fill=ink,width=3)
    else:
        tail=[(x+.69*size,y+.6*size),(x+1.09*size,y+(.73+.06*step)*size),(x+.81*size,y+.81*size)]
        d.polygon(tail,fill='#419975',outline=ink)
        for k in range(6):
            d.polygon([(x+(.31+k*.08)*size,y+.4*size),(x+(.35+k*.08)*size,y+.24*size),(x+(.4+k*.08)*size,y+.44*size)],fill='#F4BD54')
        ellipse(.24,.37,.91,.84,'#68C3A0',ink);ellipse(.31,.59,.79,.8,'#C5E9A1')
        for side in (.33,.71):ellipse(side,.71+.015*step,side+.17,.94+.015*step,'#459B79',ink)
        ellipse(.05,.24,.46,.66,'#82D7A8',ink);eye(.19,.3,.15)
        ellipse(.09,.48,.18,.53,'#F3B7A5');d.arc(box(.12,.46,.34,.6),0,160,fill=ink,width=3)
        for k in range(3):ellipse(.48+k*.1,.47,.52+k*.1,.51,'#3C9974')

def _fit_text(d,text,x,y,max_width,size,color):
    while size>16 and d.textlength(text,font=font(size))>max_width:size-=1
    d.text((x,y),text,font=font(size),fill=color,anchor='mm')

def _background(d,character,t,index):
    beach=character=='crab';garden=character=='iguana'
    # Layered gradients, moving clouds and a different environment per animal.
    top=(110,203,235);bottom=(230,250,232)
    for y in range(0,540,4):
        u=y/540;color=tuple(round(a+(b-a)*u) for a,b in zip(top,bottom))
        d.rectangle((0,y,960,y+4),fill=color)
    d.ellipse((818,66,894,142),fill='#FFF0AD');d.ellipse((828,76,884,132),fill='#FFDA67')
    for k in range(4):
        cx=(k*290+t*9+index*65)%1200-120
        d.ellipse((cx,125,cx+125,160),fill='#F5FEFA');d.ellipse((cx+30,102,cx+92,162),fill='#F5FEFA')
    d.polygon([(0,300),(175,194),(355,295),(560,186),(785,290),(960,212),(960,540),(0,540)],fill='#94D4B6')
    d.ellipse((-210,270,710,590),fill='#59B98F');d.ellipse((450,268,1230,580),fill='#77CCA1')
    if beach:
        d.rectangle((0,300,960,540),fill='#F6DFAD')
        d.rectangle((0,278,960,306),fill='#59C4CC')
        for k in range(7):
            x=k*165+math.sin(t*1.4)*18;d.arc((x,279,x+112,303),0,180,fill='#DEF8EF',width=3)
        for x,y in ((90,360),(850,365),(140,460),(815,448)):d.arc((x,y,x+22,y+15),180,360,fill='#D5B67C',width=3)
    else:
        d.ellipse((-80,312,1040,700),fill='#92D67B')
        d.ellipse((90,348,870,495),fill='#B4DD8B')
        for k in range(12):
            x=25+k*82;y=375+(k%3)*24
            d.line((x,y,x+3,y-15),fill='#54A575',width=2)
            if garden or k%3==0:
                for dx,dy in ((-5,0),(5,0),(0,-5),(0,5)):d.ellipse((x+dx-4,y-22+dy-4,x+dx+4,y-22+dy+4),fill='#FFB3A1')
                d.ellipse((x-3,y-25,x+3,y-19),fill='#FFE37B')
    for x,sign in ((35,1),(912,-1)):
        sway=math.sin(t*1.8)*5
        d.line((x,333,x+sign*12,225),fill='#668B66',width=8)
        for k in range(4):
            d.ellipse((x-42+sway,217+k*13,x+48+sway,237+k*13),fill='#3A9F79')
    # A small original butterfly crosses the sky, away from lesson text.
    bx=170+(t*24)%580;by=174+math.sin(t*2)*13;wing=5+abs(math.sin(t*9))*7
    d.ellipse((bx-wing,by-7,bx,by+7),fill='#FFB276');d.ellipse((bx,by-7,bx+wing,by+7),fill='#FFE094')
    d.line((bx,by-7,bx,by+7),fill='#5C6E69',width=2)

def frame(scene,title,index,total,t,width=960,height=540):
    im=Image.new('RGB',(960,540));d=ImageDraw.Draw(im);character=scene.get('character','shapes')
    _background(d,character,t,index)
    d.rounded_rectangle((24,18,936,78),22,fill='#244B62')
    _fit_text(d,title,480,48,860,27,'#FFFBEA')
    count=scene['count'];visible=min(count,1+int(t/.95));size=min(190,640/max(count,1));gap=26
    totalwidth=count*size+(count-1)*gap;start=480-totalwidth/2
    for k in range(visible):
        kind=('coqui','crab','iguana')[k%3] if character=='friends' else character
        age=max(0,t-k*.95);entry=min(age/.45,1);ease=1-(1-entry)**3
        x=start+k*(size+gap);ground=367
        if kind=='crab':x+=math.sin(age*1.5+k)*16
        jump=max(0,math.sin(age*3+k))*20 if kind=='coqui' else math.sin(age*2+k)*3
        y=ground-size-jump+(1-ease)*42
        d.ellipse((x+size*.12,ground-9,x+size*.94,ground+6),fill='#80AF80' if character!='crab' else '#D7C18F')
        if kind in ('coqui','crab','iguana'):_animal(d,kind,x,y,size,age+k*.55)
        else:
            box=(x,y,x+size,y+size);color=scene['color']
            if scene['shape']=='circle':d.ellipse(box,fill=color,outline='#244B62',width=3)
            elif scene['shape']=='square':d.rounded_rectangle(box,18,fill=color,outline='#244B62',width=3)
            elif scene['shape']=='triangle':d.polygon([(x+size/2,y),(x+size,y+size),(x,y+size)],fill=color,outline='#244B62')
            else:
                points=[]
                for n in range(10):
                    a=-math.pi/2+n*math.pi/5;r=size*(.5 if n%2==0 else .23);points.append((x+size/2+r*math.cos(a),y+size/2+r*math.sin(a)))
                d.polygon(points,fill=color,outline='#244B62')
        d.ellipse((x+size/2-18,366,x+size/2+18,402),fill='#FFFAE9',outline='#D5C88F',width=2)
        d.text((x+size/2,384),str(k+1),font=font(24),fill='#244B62',anchor='mm')
    d.rounded_rectangle((55,415,905,492),22,fill='#FFFBEA',outline='#D2DBC0',width=2)
    lines=textwrap.wrap(scene['text'],width=44)[:2]
    for n,line in enumerate(lines):_fit_text(d,line,480,453+(n-(len(lines)-1)/2)*31,810,30,'#244B62')
    d.rounded_rectangle((55,512,905,522),5,fill='#DBEEE1');length=850*(index+min(t/scene['duration'],1))/total
    d.rounded_rectangle((55,512,55+max(8,length),522),5,fill='#249F93')
    # Brief, gentle scene fades instead of abrupt cuts; no frame history in memory.
    fade=min(1,t/.3,max(0,(scene['duration']-t)/.3))
    if fade<1:im=Image.blend(Image.new('RGB',im.size,'#FFFBEA'),im,fade)
    if (width,height)!=(960,540):im=im.resize((width,height),Image.Resampling.LANCZOS)
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
            result=subprocess.run([ffmpeg,'-y','-v','error','-i',str(video),'-i',str(joined),'-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-metadata','comment='+plan.get('description','')[:3000],'-movflags','+faststart',str(destination)],capture_output=True,timeout=90)
            if result.returncode:raise ValueError('No pude unir narración')
        else:shutil.copyfile(video,destination)
        shutil.copyfile(destination,output)
    return {'seconds':sum(s['duration'] for s in scenes),'narration':bool(audio_paths),'path':str(output)}
