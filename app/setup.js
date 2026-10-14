'use strict';
// Field definitions for the editable profile; the first interview happens with the AI.
window.StubbsJobsSetup={
 demographics:{
  gender:{label:'Género (opcional)',type:'text',maxlength:100,placeholder:'Ej.: hombre, mujer, no binario o prefiero no responder',descriptionId:'profile-gender-help',help:'Solo se utiliza cuando el formulario lo pide y aceptas participar en su encuesta demográfica.'},
  demographicSurveyParticipation:{label:'Encuestas demográficas (opcional)',type:'choice',options:[{value:'decline',label:'Prefiero no responder'},{value:'omit',label:'No, omitirlas'},{value:'use_saved',label:'Sí, usar mis datos'}],descriptionId:'profile-demographic-help',help:'Solo para encuestas opcionales de las candidaturas que elijas.'}
 },
 contact:{email:{label:'Email',type:'text',inputType:'email',autocomplete:'email',maxlength:254},phone:{label:'Teléfono',type:'text',inputType:'tel',autocomplete:'tel',maxlength:100,placeholder:'Incluye el prefijo internacional'},currentCountry:{label:'País de residencia',type:'text',autocomplete:'country-name',maxlength:100},postalCode:{label:'Código postal',type:'text',autocomplete:'postal-code',maxlength:40},address:{label:'Dirección',type:'text',autocomplete:'street-address',maxlength:500},linkedinUrl:{label:'LinkedIn',type:'text',inputType:'url',maxlength:2000,placeholder:'https://www.linkedin.com/in/...'},websiteUrl:{label:'Web o portfolio',type:'text',inputType:'url',maxlength:2000,placeholder:'https://...'}},
 context:{name:{label:'Nombre',type:'text'},targetRoles:{label:'Puestos',type:'text',placeholder:'Ej.: enfermería, ventas, ingeniería'},keywords:{label:'Otras palabras clave',type:'text',placeholder:'Funciones, especialidades o herramientas de tu sector'},searchPriorities:{label:'Horario que prefieres',type:'longtext',rows:2,placeholder:'Horario deseado, flexibilidad o turnos que evitarías'},regions:{label:'Otras zonas',type:'text',placeholder:'Países o regiones donde buscar'},workMode:{label:'Modalidad',type:'text',placeholder:'Ej.: remoto, híbrido'},onsiteLocations:{label:'Zonas para presencial o híbrido (opcional)',type:'text',placeholder:'Ej.: Cádiz; Sevilla. Vacío = sin restricción de zona'},languages:{label:'Idiomas',type:'text',placeholder:'Ej.: inglés C1'},currency:{label:'Moneda del salario mínimo',type:'text',placeholder:'EUR o USD'},previousApplications:{label:'Solicitudes anteriores',type:'longtext',rows:3},sourceUrls:{label:'Webs exclusivas de búsqueda (opcional)',type:'longtext',rows:5},platforms:{label:'Plataformas preferidas',type:'text'}}
};
window.StubbsJobsSetup.context.searchNotes={label:'Indicaciones adicionales de búsqueda',type:'longtext',rows:3,maxlength:3000,placeholder:'Orientación, puestos que evitar o preparación que aceptarías. No autoriza candidaturas.'};
// Reviewed presentations keep the original stored keys, types and consent scopes.
window.StubbsJobsSetup.aboutOptions={
 permissions:[
  {key:'custom_recruitment_retention_365d',label:'Selección y conservación hasta 365 días',short:'Hasta 365 días'},
  {key:'custom_selection_processing_outside_eu',label:'Selección en centros fuera de la UE, sin plazo indicado',short:'Fuera de la UE, sin plazo indicado'}
 ],
 choices:{
  gender:[{value:'Hombre',label:'Hombre'},{value:'Mujer',label:'Mujer'},{value:'No binario',label:'No binario'},{value:'Prefiero no responder',label:'Prefiero no responder'}],
  custom_legally_protected_status:[{value:'Sí',label:'Sí'},{value:'No',label:'No'}]
 },
 details:{custom_programming_competitions_hackathons:'custom_programming_competitions_results'}
};
