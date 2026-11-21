export const clamp = (n,min=0,max=1)=>Math.max(min,Math.min(max,n));
export const cubic = (a,b,c,d,t)=>{
  const u=1-t;
  return {x:u*u*u*a.x+3*u*u*t*b.x+3*u*t*t*c.x+t*t*t*d.x,
    y:u*u*u*a.y+3*u*u*t*b.y+3*u*t*t*c.y+t*t*t*d.y};
};
// All water trajectories are vetted, data-independent and deterministic.
export const evaporation = (t,lane=0)=>cubic({x:720+lane*25,y:760},{x:820,y:560},{x:680,y:330},{x:520+lane*12,y:240},clamp(t));
export const runoff = t=>cubic({x:360,y:575},{x:390,y:705},{x:570,y:690},{x:755,y:805},clamp(t));
export const phaseAt = (scenes,seconds)=>scenes.find(s=>seconds>=s.start_seconds&&seconds<s.end_seconds)||scenes.at(-1);
export const localAsset = value=>value===null || (typeof value==='string'&&/^generated\/[a-z0-9_-]+\.(jpg|png|wav)$/.test(value));
