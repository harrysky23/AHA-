import test from 'node:test';
import assert from 'node:assert/strict';
import {evaporation,runoff,phaseAt,localAsset} from '../src/motion.mjs';

test('water vapor rises and runoff moves downhill in screen coordinates',()=>{
  for(let i=1;i<=100;i++){
    assert.ok(evaporation(i/100).y<evaporation((i-1)/100).y);
    assert.ok(runoff(i/100).y>=runoff((i-1)/100).y);
  }
});
test('same frame-time gives exactly the same coordinates',()=>{
  assert.deepEqual(evaporation(.234),evaporation(.234));
  assert.notDeepEqual(evaporation(.234),evaporation(.235));
});
test('only generated local media can be referenced',()=>{
  for(const s of ['https://example.test/x.jpg','../a.jpg','generated/../a.jpg','file:///a.wav','javascript:alert(1)']) assert.equal(localAsset(s),false);
  assert.equal(localAsset('generated/background.jpg'),true);assert.equal(localAsset(null),true);
});
test('boundary selects next scene, not overlapping animation',()=>{
  const scenes=[{id:'a',start_seconds:0,end_seconds:2},{id:'b',start_seconds:2,end_seconds:4}];
  assert.equal(phaseAt(scenes,2).id,'b');assert.equal(phaseAt(scenes,1.99).id,'a');
});
