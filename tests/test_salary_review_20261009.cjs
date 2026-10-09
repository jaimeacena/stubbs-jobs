'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const F=require('../app/formatting.js');

test('published ranges preserve both endpoints with currencies and natural connectors',()=>{
 for(const [raw,low,high,currency] of [
  ['35.000 € - 45.000 €',35000,45000,'EUR'],
  ['Entre 35.000 y 45.000 euros brutos anuales',35000,45000,'EUR'],
  ['35k GBP to 45k GBP per year',35000,45000,'GBP'],
  ['USD 35,000 to USD 45,000 annually',35000,45000,'USD']]){
  const info=F.salaryInfo(raw);
  assert.equal(info.kind,'range',raw);assert.equal(info.low,low,raw);
  assert.equal(info.high,high,raw);assert.equal(info.currency,currency,raw);
  assert.equal(info.raw,raw);
 }
});

test('English ceilings and floors do not become an exact salary',()=>{
 const ceiling=F.salaryInfo('Up to 50k EUR annually');
 assert.equal(ceiling.kind,'ceiling');assert.equal(ceiling.low,null);assert.equal(ceiling.high,50000);
 assert.equal(F.salaryNumber(ceiling.raw),null);
 const floor=F.salaryInfo('Starting at 35k EUR per year');
 assert.equal(floor.kind,'floor');assert.equal(floor.low,35000);assert.equal(floor.high,null);
});

test('a bonus ceiling does not rewrite the published fixed salary as a ceiling',()=>{
 const info=F.salaryInfo('35.000 EUR fijos más variable de hasta 5.000 EUR');
 assert.equal(info.kind,'point');assert.equal(info.low,35000);assert.equal(info.note,'Incluye variable');
});
