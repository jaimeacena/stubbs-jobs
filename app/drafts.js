'use strict';
// Durable attempts retain the exact operation until its result is known.
(() => {
  function settle(current, attempt) {
    if (JSON.stringify(current.values) === JSON.stringify(attempt.values)) return null;
    const saved=attempt.operation.values || (attempt.operation.kind==='ui-experience'?{text:attempt.operation.text}:{});
    return {...current, expected:{...current.expected,...saved}, shown:{...current.shown,...saved}, attempt:null};
  }
  function migrate(session, durable) {
    const prefix='stubbs_jobs-draft:';
    const persisted=(store,key)=>typeof store.isPersistent!=='function'||store.isPersistent(key);
    for(const store of [session,durable]) {
      if(typeof store.length!=='number'||typeof store.key!=='function')continue;
      for(let i=store.length-1;i>=0;i--) {
        const oldKey=store.key(i),marker=oldKey?.indexOf('-draft:');
        if(typeof oldKey!=='string'||marker<0||oldKey.startsWith(prefix)||oldKey.startsWith('stubbs_jobs-workspace:'))continue;
        try {
          const value=store.getItem(oldKey),draft=JSON.parse(value);
          if(!draft||typeof draft.values!=='object'||typeof draft.expected!=='object'||typeof draft.shown!=='object')continue;
          let suffix=oldKey.slice(marker+7);
          if(suffix==='perfil:global'&&('applicationMode' in draft.values||'searchFrequency' in draft.values))suffix='ajustes:global';
          const nextKey=prefix+suffix;
          if(store.getItem(nextKey)===null)store.setItem(nextKey,value);
          if(persisted(store,nextKey)&&store.getItem(nextKey)===value)store.removeItem(oldKey);
        }catch{}
      }
      const oldKey=prefix+'ajustes:global',raw=store.getItem(oldKey);
      if(raw!==null){try{
        const draft=JSON.parse(raw);
        if(draft&&typeof draft.values==='object'){
          let copied=false,collision=false;
          for(const [target,keys] of [['opciones-solicitud',['applicationMode','contactMode']],['programacion',['searchTime','scheduleEnabled']]]){
            const values=Object.fromEntries(Object.entries(draft.values).filter(([key])=>keys.includes(key)));
            if(target==='programacion'&&'searchFrequency' in draft.values&&!('scheduleEnabled' in values))values.scheduleEnabled=draft.values.searchFrequency==='daily'?'true':'false';
            if(!Object.keys(values).length)continue;
            const next=prefix+target+':global';
            const migrated=JSON.stringify({...draft,values,expected:Object.fromEntries(Object.entries(draft.expected).filter(([key])=>keys.includes(key))),shown:Object.fromEntries(Object.entries(draft.shown).filter(([key])=>keys.includes(key))),attempt:null});
            if(store.getItem(next)===null)store.setItem(next,migrated);
            else if(store.getItem(next)!==migrated)collision=true;
            if(!persisted(store,next))collision=true;
            copied=true;
          }
          if(copied&&!collision&&!draft.attempt)store.removeItem(oldKey);
        }
      }catch{}}
      for(const [from,to,fields] of [['datos','busqueda',['languages','salaryExpectationFixed']],['antecedentes','busqueda',['previousApplications']]]) {
        const sourceKey=prefix+from+':global',targetKey=prefix+to+':global',sourceRaw=store.getItem(sourceKey);
        if(sourceRaw===null)continue;
        try {
          const source=JSON.parse(sourceRaw),targetRaw=store.getItem(targetKey),target=targetRaw===null?{values:{},expected:{},shown:{},attempt:null}:JSON.parse(targetRaw);
          if(source?.attempt||target?.attempt||!source?.values||!target?.values)continue;
          let moved=false;
          for(const field of fields) {
            if(!Object.hasOwn(source.values,field)||Object.hasOwn(target.values,field))continue;
            for(const part of ['values','expected','shown'])if(Object.hasOwn(source[part]||{},field)){
              target[part][field]=source[part][field];delete source[part][field];
            }
            moved=true;
          }
          if(!moved)continue;
          store.setItem(targetKey,JSON.stringify(target));
          if(!persisted(store,targetKey))continue;
          if(Object.keys(source.values).length)store.setItem(sourceKey,JSON.stringify(source));else store.removeItem(sourceKey);
        }catch{}
      }
    }
  }
  // Each open tab owns its attempts; the shared copy is only crash recovery.
  function storage(session, durable) {
    const known=new Set();
    return {
      keys(){return [...new Set([...known,...[session,durable].flatMap(store=>Array.from({length:store.length||0},(_,i)=>store.key(i)).filter(key=>typeof key==='string'))])];},
      isPersistent(key){return typeof durable.isPersistent!=='function'||durable.isPersistent(key);},
      getItem(key) {
        if(!known.has(key)) {
          known.add(key);
          if(session.getItem(key)===null) {
            const saved=durable.getItem(key);
            if(saved!==null)session.setItem(key,saved);
          }
        }
        return session.getItem(key);
      },
      setItem(key,value) {known.add(key);session.setItem(key,value);durable.setItem(key,value);},
      removeItem(key) {known.add(key);const own=session.getItem(key);session.removeItem(key);if(durable.getItem(key)===own)durable.removeItem(key);}
    };
  }
  function bindSearchProfile(store,identifier){
    for(const section of ['busqueda','fuentes']){
      const old='stubbs_jobs-draft:'+section+':global',next='stubbs_jobs-draft:'+section+':profile:'+identifier,raw=store.getItem(old);
      if(raw===null||store.getItem(next)!==null)continue;
      // Retain the exact old attempt; an ambiguous old operation cannot silently
      // gain a different scope. The writer will require an explicit identifier.
      store.setItem(next,raw);
      if((typeof store.isPersistent!=='function'||store.isPersistent(next))&&store.getItem(next)===raw)store.removeItem(old);
    }
  }

  function pending(store){
    const keys=typeof store.keys==='function'?store.keys():Array.from({length:store.length||0},(_,i)=>store.key(i));
    const object=value=>!!value&&typeof value==='object'&&!Array.isArray(value);
    const comparable=value=>value===null||value===undefined?'':String(value);
    return keys.filter(key=>/^stubbs_jobs-draft:[^:]+:.+$/.test(key||'')).flatMap(key=>{
      try{
        const draft=JSON.parse(store.getItem(key));
        if(!object(draft)||!object(draft.values)||!object(draft.shown))return [];
        if(!draft.attempt&&!Object.entries(draft.values).some(([field,value])=>comparable(value)!==comparable(draft.shown[field])))return [];
        return [{key}];
      }catch{return [];}
    });
  }

  function scoped(store,workspace){
    const prefix='stubbs_jobs-workspace:'+encodeURIComponent(workspace)+':';
    const keys=()=>Array.from({length:store.length||0},(_,i)=>store.key(i)).filter(key=>key?.startsWith(prefix));
    return {
      get length(){return keys().length;},key:i=>keys()[i]?.slice(prefix.length)??null,
      getItem:key=>store.getItem(prefix+key),setItem:(key,value)=>store.setItem(prefix+key,value),removeItem:key=>store.removeItem(prefix+key),
      isPersistent:key=>typeof store.isPersistent!=='function'||store.isPersistent(prefix+key)
    };
  }

  function legacyDrafts(session,durable){
    const found=new Map();
    for(const store of [durable,session]){
      for(let i=0;i<(store.length||0);i++){
        const key=store.key(i);
        if(!/^stubbs_jobs-draft:(datos|experiencia|busqueda|fuentes):global$/.test(key||''))continue;
        try{
          const raw=store.getItem(key),value=JSON.parse(raw);
          const object=x=>!!x&&typeof x==='object'&&!Array.isArray(x);
          if(!object(value)||!['values','expected','shown'].every(part=>object(value[part])))continue;
          found.set(key+'\n'+raw,{key,value});
        }catch{}
      }
    }
    return [...found.values()];
  }

  function recoverLegacy(store,item){
    if(store.getItem(item.key)!==null)throw new Error('Ya hay un borrador en esta sección. Guárdalo antes de recuperar otro.');
    // An unknown workspace cannot grant a replay of an old save.
    store.setItem(item.key,JSON.stringify({...item.value,attempt:null}));
  }

  function actionJournal(store){
    const stable=value=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):Array.isArray(value)?value.map(stable):value;
    const key=operation=>'stubbs_jobs-action:'+JSON.stringify(stable(operation));
    return {
      begin(operation,newId){
        const name=key(operation);let saved;
        try{saved=JSON.parse(store.getItem(name));}catch{}
        if(saved?.id&&JSON.stringify(stable(saved.operation))===JSON.stringify(stable(operation)))return saved;
        const attempt={id:newId(),operation:JSON.parse(JSON.stringify(operation))};
        store.setItem(name,JSON.stringify(attempt));return attempt;
      },
      finish(operation){store.removeItem(key(operation));}
    };
  }
  const api={settle,storage,pending,migrate,scoped,legacyDrafts,recoverLegacy,actionJournal,bindSearchProfile};
  if(typeof module!=='undefined')module.exports=api;
  else window.StubbsJobsDrafts=api;
})();
