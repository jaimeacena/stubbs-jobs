'use strict';
// Decorative vectors; controls provide visible text or an accessible name.
(() => {
 const shapes=Object.freeze({
  eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  bot:'<rect x="4" y="7" width="16" height="14" rx="4"/><path d="M12 3v4M2 11v6m20-6v6M9 17h6"/><path d="M8.5 12h.01m7 0h.01" stroke-width="3"/>',
  'arrow-right':'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  'arrow-left':'<path d="M19 12H5m6-6-6 6 6 6"/>',
  'arrow-up-right':'<path d="M7 17 17 7M7 7h10v10"/>',
  'chevron-right':'<path d="m9 5 7 7-7 7"/>',
  'chevron-left':'<path d="m15 5-7 7 7 7"/>',
  'chevron-down':'<path d="m5 9 7 7 7-7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  archive:'<rect x="3" y="3" width="18" height="4" rx="1"/><path d="M5 7v14h14V7M10 11h4"/>',
  question:'<path d="M8 7a4 4 0 0 1 8 0c0 3-4 3-4 6v2M12 19v1"/>',
  bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  trophy:'<path d="M8 3h8v6a4 4 0 0 1-8 0V3ZM8 5H4v2a4 4 0 0 0 4 4m8-6h4v2a4 4 0 0 1-4 4M12 13v5m-4 3h8m-6-3h4v3h-4Z"/>',
  send:'<path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  building:'<path d="M4 21V4h11v17m0-11h5v11M2 21h20M8 8h3m-3 4h3m-3 4h3m6-2v3"/>',
  file:'<path d="M6 3h8l4 4v14H6Zm8 0v5h4M9 12h6m-6 4h6"/>',
  filter:'<path d="M3 4h18l-7 8v7l-4 2v-9Z"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  pencil:'<path d="m14 5 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-4-4L5 15l-1 5Z"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>'
 });
 const solidShapes=Object.freeze({
  archive:'<path fill-rule="evenodd" d="M3 3h18v5H3V3Zm2 7h14v11H5V10Zm5 3v2h4v-2h-4Z"/>',
  question:'<path d="M12 2C7.9 2 5 4.6 5 8h4c0-1.5 1.2-2.5 3-2.5s3 1 3 2.5c0 1.1-.6 1.7-2.1 2.7C10.9 12 10 13.4 10 16h4c0-1.5.5-2.1 2.2-3.2C18.1 11.5 19 10 19 7.7 19 4.4 16.1 2 12 2ZM10 18h4v4h-4Z"/>',
  bell:'<path d="M12 2a7 7 0 0 1 7 7v5l3 4H2l3-4V9a7 7 0 0 1 7-7ZM9 20h6a3 3 0 0 1-6 0Z"/>',
  check:'<path d="m2 12 3-3 5 5L19 4l3 3-12 13-8-8Z"/>',
  lock:'<path fill-rule="evenodd" d="M7 10V7a5 5 0 0 1 10 0v3h2v12H5V10h2Zm3 0h4V7a2 2 0 0 0-4 0v3Z"/>',
  close:'<path d="m5 2 7 7 7-7 3 3-7 7 7 7-3 3-7-7-7 7-3-3 7-7-7-7 3-3Z"/>',
  trophy:'<path fill-rule="evenodd" d="M7 2h10v2h5v4a7 7 0 0 1-6 7l-2 1v3h4v3H6v-3h4v-3l-2-1a7 7 0 0 1-6-7V4h5V2Zm0 5H5v1c0 2 1 3 2 4V7Zm10 0v5c1-1 2-2 2-4V7h-2Z"/>',
  file:'<path fill-rule="evenodd" d="M5 2h9l5 5v15H5V2Zm9 3v3h3l-3-3Z"/>',
  send:'<path d="m2 2 20 10L2 22v-7l11-3L2 9V2Z"/>'
 });
 function icon(name,className='ui-icon',style='outline') {
  if(!['outline','solid'].includes(style))throw new Error('Estilo de icono desconocido');
  const selected=style==='solid'?solidShapes:shapes;
  if(!Object.hasOwn(selected,name))throw new Error('Icono desconocido: '+name);
  // Only internal CSS class names are accepted; user strings never become markup.
  if(!/^[\w -]*$/.test(className))throw new Error('Clase de icono no válida');
  return `<svg class="${className}" data-icon="${name}" viewBox="0 0 24 24" width="20" height="20" fill="${style==='solid'?'currentColor':'none'}" stroke="${style==='solid'?'none':'currentColor'}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${selected[name]}</svg>`;
 }
 const api=Object.freeze({icon});
 if(typeof module!=='undefined')module.exports=api;else window.StubbsJobsIcons=api;
})();
