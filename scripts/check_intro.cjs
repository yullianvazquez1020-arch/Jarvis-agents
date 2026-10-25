/* The intro runs in desktop/app.py. A second browser/tab must never replay it.
   Native playback, cancellation and cleanup are checked in test_voice_recovery.py. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('desktop/ui/arranque.js','utf8');

function harness(owner) {
  const calls=[];
  const forbidden=name=>(...args)=>{calls.push(name);throw new Error(`Browser intro attempted ${name}`);};
  const window={JarvisAudioOwner:owner,JarvisIntroBusy:true};
  const context={window,
    Audio:forbidden('Audio'),AudioContext:forbidden('AudioContext'),
    fetch:forbidden('fetch'),setTimeout:forbidden('timer'),setInterval:forbidden('interval'),
    navigator:{mediaDevices:{getUserMedia:forbidden('microphone')}},
    document:{addEventListener:forbidden('document event'),getElementById:forbidden('DOM access')},
    addEventListener:forbidden('window event')};
  vm.runInNewContext(source,context);
  assert.equal(window.JarvisIntroBusy,false);
  assert.equal(typeof window.JarvisStopIntro,'function');
  assert.equal(typeof window.JarvisAmbience.duck,'function');
  window.JarvisStopIntro();window.JarvisStopIntro();
  window.JarvisAmbience.duck(true);window.JarvisAmbience.duck(false);
  assert.equal(window.JarvisIntroBusy,false);
  assert.deepEqual(calls,[]);
}

for (const owner of [true,false,null]) harness(owner);
console.log('PASS: browser tabs never replay the native intro, hold the microphone, or start background audio; compatibility hooks remain callable.');
