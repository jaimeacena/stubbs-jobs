const test=require('node:test'),assert=require('node:assert/strict');
const Criteria=require('../app/criteria.js');
const none={toEligible:[],toDiscarded:[],assessments:[],fitReviews:[],packages:[],authorizedPackages:[],excluded:['sent']};

test('a save without effect and without earlier rounds does not ask anything',()=>{
 const result=Criteria.summary(none,null,[]);
 assert.equal(result.needed,false);assert.deepEqual(result.lines,[]);assert.equal(result.rounds,null);
});
test('the effect on offers judged with current criteria is stated in counts',()=>{
 const effect={...none,toDiscarded:['a','b'],toEligible:['c'],assessments:['a'],fitReviews:['a','c'],packages:['a'],authorizedPackages:['a']};
 const result=Criteria.summary(effect,null,[]);
 assert.equal(result.needed,true);
 assert.deepEqual(result.lines,['2 ofertas pasarán a descartadas','1 oferta volverá a Por decidir',
  'La valoración de 2 ofertas dejará de estar al día',
  '1 solicitud preparada tendrá que revisarse (una tenía tu autorización de envío y no se enviará sin revisarla de nuevo)']);
 assert.doesNotMatch(result.lines.join(' '),/%/);
});
test('earlier rounds are offered only with the additional effect of moving them',()=>{
 const current={...none,assessments:['old']};
 const moved={...none,toEligible:['old'],assessments:['old']};
 const result=Criteria.summary(current,moved,['old']);
 assert.equal(result.needed,true);
 assert.deepEqual(result.rounds.ids,['old']);
 assert.match(result.rounds.label,/1 oferta encontrada en búsquedas anteriores/);
 assert.match(result.rounds.note,/1 oferta volverá a Por decidir\.$/);
 assert.doesNotMatch(result.rounds.note,/valoración/);
});
test('rounds that would not change are only mentioned, not offered',()=>{
 const result=Criteria.summary(none,none,['old','older']);
 assert.equal(result.needed,false);assert.equal(result.rounds,null);
 assert.match(result.keep,/2 ofertas de búsquedas anteriores conservan sus criterios y no cambian/);
});
test('round offers are those judged with their round criteria',()=>{
 assert.deepEqual(Criteria.roundOffers([{id:'a',criteriaScope:'round'},{id:'b',criteriaScope:'current'},{id:'c'}]),['a']);
});
