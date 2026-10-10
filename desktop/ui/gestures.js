/* Gestos visuales locales. Sin teclado ni órdenes al sistema. */
(function(root) {
  "use strict";
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  function pose(points) {
    if (!Array.isArray(points) || points.length!==21 || !points.every(p=>p && Number.isFinite(p.x) && Number.isFinite(p.y))) return null;
    const palm=distance(points[5],points[17]);
    if(palm<.02)return null;
    const fingers=[[8,6],[12,10],[16,14],[20,18]].map(([tip,joint])=>distance(points[tip],points[0])>distance(points[joint],points[0])*1.15);
    const count=fingers.filter(Boolean).length;
    return {pinch:distance(points[4],points[8])/palm<.4, center:points[5],
      command:count===0?'pause':count===4?'resume':fingers[0]&&fingers[1]&&!fingers[2]&&!fingers[3]?'next':null};
  }
  function zoomDistance(hands) {
    if(!Array.isArray(hands)||hands.length!==2)return null;
    const poses=hands.map(h=>pose(h.landmarks));
    if(!poses.every(p=>p&&p.pinch))return null;
    const d=distance(poses[0].center,poses[1].center);
    return d>.08?d:null;
  }
  root.JarvisGestures={pose,zoomDistance};
})(typeof window==='undefined'?globalThis:window);
