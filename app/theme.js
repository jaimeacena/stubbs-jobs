'use strict';
(()=>{
 const key='stubbs_jobs-theme';
 const valid=['system','light','dark'];
 const read=()=>{try{const value=localStorage.getItem(key);return valid.includes(value)?value:'system';}catch{return 'system';}};
 function set(value){
  if(!valid.includes(value))return;
  if(value==='system')document.documentElement.removeAttribute('data-theme');
  else document.documentElement.dataset.theme=value;
  try{localStorage.setItem(key,value);}catch{}
  document.querySelectorAll?.('button[data-theme]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.theme===value)));
 }
 window.StubbsJobsTheme={get:read,set};
 set(read());
})();
