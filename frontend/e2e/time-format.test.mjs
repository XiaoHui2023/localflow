import test from 'node:test';
import assert from 'node:assert/strict';
import { showTime, localInputValue, parseLocalTime } from '../src/time.js';

test('24-hour rendering includes midnight and afternoon without meridiem markers',()=>{
 assert.match(showTime(new Date(2026,8,29,20,8,0)),/20:08:00/);
 assert.match(showTime(new Date(2026,8,29,0,8,0)),/00:08:00/);
 assert.equal(localInputValue(new Date(2026,8,29,20,8,0)),'2026-09-29 20:08:00');
});

test('calibration preserves local time and rejects partial or normalized impossible dates',()=>{
 const parsed=parseLocalTime('2026-09-29 20:08:00');
 assert.equal(parsed.getHours(),20);
 assert.equal(localInputValue(parsed),'2026-09-29 20:08:00');
 for(const invalid of ['2026-02-30 20:08:00','2026-09-29 24:08:00','2026-09-29 20:08','下午 08:08',''])
  assert.equal(parseLocalTime(invalid),null);
});
