'use strict';
// Read-only wording of what saving new criteria would do; the server computes the effect.
(() => {
  const effectKeys=['toEligible','toDiscarded','assessments','fitReviews','packages','authorizedPackages'];
  const plural=(n,one,many)=>`${n} ${n===1?one:many}`;
  // Offers judged with the criteria of the search that found them.
  const roundOffers=jobs=>(jobs||[]).filter(j=>j.criteriaScope==='round').map(j=>j.id);
  // Effect on round offers that the plain save does not already cause.
  function extra(current,moved){
    const result={};
    for(const key of effectKeys){const seen=new Set(current?.[key]||[]);result[key]=(moved?.[key]||[]).filter(id=>!seen.has(id));}
    return result;
  }
  const empty=effect=>effectKeys.every(key=>!(effect?.[key]||[]).length);
  function lines(effect){
    const valuations=new Set([...(effect.assessments||[]),...(effect.fitReviews||[])]).size;
    const out=[];
    if(effect.toDiscarded?.length)out.push(plural(effect.toDiscarded.length,'oferta pasará a descartada','ofertas pasarán a descartadas'));
    if(effect.toEligible?.length)out.push(plural(effect.toEligible.length,'oferta volverá a Por decidir','ofertas volverán a Por decidir'));
    if(valuations)out.push(`La valoración de ${plural(valuations,'oferta','ofertas')} dejará de estar al día`);
    if(effect.packages?.length){
      let text=plural(effect.packages.length,'solicitud preparada tendrá que revisarse','solicitudes preparadas tendrán que revisarse');
      const authorized=effect.authorizedPackages?.length||0;
      if(authorized)text+=` (${authorized===1?'una tenía':authorized+' tenían'} tu autorización de envío y no se enviará${authorized===1?'':'n'} sin revisarla${authorized===1?'':'s'} de nuevo)`;
      out.push(text);
    }
    return out;
  }
  // current: preview of the save; moved: preview of the save plus moving round offers to it.
  function summary(current,moved,rounds){
    const added=moved?extra(current,moved):null;
    const offer=!!(rounds?.length&&added&&!empty(added));
    const now=lines(current||{});
    return {needed:now.length>0||offer,
      intro:now.length?'Al guardar, las ofertas que se juzgan con tus criterios actuales se reevalúan:':'Las ofertas que se juzgan con tus criterios actuales no cambian.',
      lines:now,
      rounds:offer?{ids:rounds,label:`Aplicar también a ${plural(rounds.length,'oferta encontrada','ofertas encontradas')} en búsquedas anteriores`,
        note:`Ahora conservan los criterios con que se encontraron. Si los aplicas: ${lines(added).map(t=>t[0].toLowerCase()+t.slice(1)).join('; ')}.`}:null,
      keep:rounds?.length&&!offer?`${plural(rounds.length,'oferta de búsquedas anteriores conserva','ofertas de búsquedas anteriores conservan')} sus criterios y no cambia${rounds.length===1?'':'n'}.`:''};
  }
  const api={roundOffers,extra,lines,summary};
  if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsCriteria=api;
})();
