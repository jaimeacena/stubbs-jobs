'use strict';
// Browser persistence and HTTP failures are isolated from product decisions.
(() => {
  function safeStorage(open, onFailure=()=>{}) {
    const memory=new Map(),volatile=new Set();
    let store;
    try{store=open();}catch{onFailure();}
    return {
      isPersistent(key){return Boolean(store)&&!volatile.has(key);},
      get length(){return keys().length;},
      key(index){return keys()[index]??null;},
      getItem(key){
        if(volatile.has(key))return memory.get(key)??null;
        try{if(store){const value=store.getItem(key);if(value===null)memory.delete(key);else memory.set(key,value);return value;}}
        catch{onFailure();}
        return memory.get(key)??null;
      },
      setItem(key,value){
        memory.set(key,String(value));
        try{if(!store)throw new Error();store.setItem(key,String(value));volatile.delete(key);}
        catch{volatile.add(key);onFailure();}
      },
      removeItem(key){
        memory.delete(key);
        try{if(!store)throw new Error();store.removeItem(key);volatile.delete(key);}
        catch{volatile.add(key);onFailure();}
      }
    };
    function keys(){
      let found=new Set(memory.keys());
      try{if(store){const durable=new Set();for(let i=0;i<store.length;i++){const key=store.key(i);if(key!==null&&!volatile.has(key))durable.add(key);}found=new Set([...durable,...[...volatile].filter(key=>memory.has(key))]);}}
      catch{onFailure();}
      return [...found].filter(key=>!volatile.has(key)||memory.has(key));
    }
  }

  function validateState(data){
    const object=value=>!!value&&typeof value==='object'&&!Array.isArray(value);
    if(!object(data)||!Number.isInteger(data.revision)||data.revision<0||typeof data.setupComplete!=='boolean'||
       !['profile','preferences','searchContext','execution','snoozes'].every(key=>object(data[key]))||
       !['opportunities','requests','history','health'].every(key=>Array.isArray(data[key]))||
       typeof data.workspaceId!=='string'||!data.workspaceId||data.workspaceId.length>100||
       !data.opportunities.every(row=>object(row)&&typeof row.id==='string'&&Array.isArray(row.requests)&&Array.isArray(row.packages)&&Array.isArray(row.questions)&&Array.isArray(row.missing))){
      throw new Error('No se pudo leer el estado completo. Tu trabajo se conserva; vuelve a actualizar la app.');
    }
    if(data.onboarding!==undefined){
      const setup=data.onboarding;
      if(!object(setup)||!['waiting','access_checked','preparing','awaiting_confirmation','blocked','ready'].includes(setup.status)||
         typeof setup.token!=='string'||!setup.token||!Number.isInteger(setup.revision)||setup.revision<0||
         setup.workspaceId!==data.workspaceId||typeof setup.needsWelcome!=='boolean'||typeof setup.summary!=='string'){
        throw new Error('No se pudo leer la preparación inicial. Actualiza el estado para continuar.');
      }
    }
    return data;
  }

  async function request(path, body, {fetcher=globalThis.fetch, timeout=30000}={}) {
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),timeout);
    try{
      const response=await fetcher(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-StubbsJobs':'1'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store',signal:controller.signal});
      let data;
      try{data=await response.json();}
      catch{throw new Error('La app devolvió una respuesta incompleta. Actualiza el estado antes de continuar.');}
      if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('No se pudo interpretar la respuesta de la app. Actualiza el estado.');
      if(!response.ok){const error=new Error(data.error||'No se pudo completar la acción');error.status=response.status;error.state=data.state;throw error;}
      return data;
    }catch(error){
      if(controller.signal.aborted)throw new Error(body?'La acción tarda demasiado. Tu borrador se conserva; actualiza el estado para comprobar el resultado.':'La app tarda en responder. Vuelve a actualizar el estado.');
      if(error instanceof TypeError)throw new Error('No hay conexión con Stubbs Jobs. Abre la app desde su acceso y vuelve a intentarlo.');
      throw error;
    }finally{clearTimeout(timer);}
  }
  const api={safeStorage,request,validateState};
  if(typeof module!=='undefined')module.exports=api;
  else window.StubbsJobsClient=api;
})();
