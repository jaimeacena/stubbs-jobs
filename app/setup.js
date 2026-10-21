'use strict';
// Field definitions for the editable profile; the first interview happens with the AI.
window.StubbsJobsSetup={
 demographics:{
  gender:{label:'Género (opcional)',type:'text',maxlength:100,placeholder:'Ej.: hombre, mujer, no binario o prefiero no responder',descriptionId:'profile-gender-help',help:'Solo se utiliza cuando el formulario lo pide y aceptas participar en su encuesta demográfica.'},
  demographicSurveyParticipation:{label:'Encuestas demográficas (opcional)',type:'choice',options:[{value:'decline',label:'Prefiero no responder'},{value:'omit',label:'No, omitirlas'},{value:'use_saved',label:'Sí, usar mis datos'}],descriptionId:'profile-demographic-help',help:'Solo para encuestas opcionales de las candidaturas que elijas.'}
 },
 contact:{email:{label:'Email',type:'text',inputType:'email',autocomplete:'email',maxlength:254},phone:{label:'Teléfono',type:'text',inputType:'tel',autocomplete:'tel',maxlength:100,placeholder:'Incluye el prefijo internacional'},currentCountry:{label:'País de residencia',type:'text',autocomplete:'country-name',maxlength:100},postalCode:{label:'Código postal',type:'text',autocomplete:'postal-code',maxlength:40},address:{label:'Dirección',type:'text',autocomplete:'street-address',maxlength:500},linkedinUrl:{label:'LinkedIn',type:'text',inputType:'url',maxlength:2000,placeholder:'https://www.linkedin.com/in/...'},websiteUrl:{label:'Web o portfolio',type:'text',inputType:'url',maxlength:2000,placeholder:'https://...'}},
 context:{name:{label:'Nombre',type:'text'},targetRoles:{label:'Puestos',type:'text',placeholder:'Ej.: enfermería, ventas, ingeniería'},keywords:{label:'Otras palabras clave',type:'text',placeholder:'Funciones, especialidades o herramientas de tu sector'},searchPriorities:{label:'Horario que prefieres',type:'longtext',rows:2,placeholder:'Horario deseado, flexibilidad o turnos que evitarías'},requiredSchedule:{label:'Horario obligatorio',type:'choice',emptyLabel:'Sin requisito',options:[{value:'morning',label:'Solo de mañana'},{value:'afternoon',label:'Solo de tarde'},{value:'continuous',label:'Jornada continua, sin partida'}],help:'La oferta se descarta si el anuncio publica un horario incompatible o no confirma este horario. Vuelve a Por solicitar cuando conste un horario compatible.'},regions:{label:'Otras zonas',type:'text',placeholder:'Países o regiones donde buscar'},workMode:{label:'Modalidad',type:'text',placeholder:'Ej.: remoto, híbrido'},onsiteLocations:{label:'Zonas para presencial o híbrido (opcional)',type:'text',placeholder:'Ej.: Cádiz; Sevilla. Vacío = sin restricción de zona'},languages:{label:'Idiomas',type:'text',placeholder:'Ej.: inglés C1'},currency:{label:'Moneda del salario mínimo',type:'text',placeholder:'EUR o USD'},previousApplications:{label:'Solicitudes anteriores',type:'longtext',rows:3},sourceUrls:{label:'Webs exclusivas de búsqueda (opcional)',type:'longtext',rows:5},platforms:{label:'Plataformas preferidas',type:'text'}}
};
window.StubbsJobsSetup.context.searchNotes={label:'Otras indicaciones para el agente',type:'longtext',rows:3,maxlength:3000,placeholder:'Orientación, puestos que evitar o preparación que aceptarías. No autoriza candidaturas.'};
// Reviewed presentations keep the original stored keys, types and consent scopes.
window.StubbsJobsSetup.aboutOptions={
 permissions:[
  {key:'custom_recruitment_retention_365d',label:'Conservar hasta 1 año',help:'La empresa puede guardar tu CV y contacto para selección hasta 365 días.',short:'Hasta 1 año'},
  {key:'custom_recruitment_retention_5y',label:'Conservar hasta 5 años',help:'La empresa puede guardar tu CV y contacto para selección hasta 5 años.',short:'Hasta 5 años'},
  {key:'custom_selection_processing_outside_eu',label:'Selección fuera de la UE',help:'Centros de selección fuera de la UE, aunque el aviso no indique plazo.',short:'Fuera de la UE'}
 ],
 choices:{
  gender:[{value:'Hombre',label:'Hombre'},{value:'Mujer',label:'Mujer'},{value:'No binario',label:'No binario'},{value:'Prefiero no responder',label:'Prefiero no responder'}],
  custom_legally_protected_status:[{value:'Sí',label:'Sí'},{value:'No',label:'No'}]
 },
 details:{custom_programming_competitions_hackathons:'custom_programming_competitions_results'}
};
// Standing permissions for Auto-solicitud; keys and meaning match tools/app_workflow.py AUTO_APPLY_FIELDS.
window.StubbsJobsSetup.autoApplyPermissions=[
 {key:'autoApplySubmit',label:'Envío final sin preguntar',help:'Envía las ofertas que elijas en Auto-solicitud sin pedirte una última confirmación.',short:'Envío sin preguntar'},
 {key:'autoApplyPrivacy',label:'Avisos de privacidad',help:'Acepta el tratamiento de tus datos solo para la selección de esa oferta.',short:'Privacidad'},
 {key:'autoApplyTerms',label:'Condiciones del portal',help:'Acepta las necesarias para presentar la solicitud; nunca pagos ni suscripciones.',short:'Condiciones'},
 {key:'autoApplyDerivedAnswers',label:'Respuestas deducidas',help:'Responde lo que se deduce sin duda de tus datos: años de experiencia, Sí/No, nivel de idioma.',short:'Respuestas deducidas'},
 {key:'autoApplySessions',label:'Sesiones abiertas',help:'Usa tus sesiones del navegador del agente (LinkedIn, InfoJobs…).',short:'Sesiones'},
 {key:'autoApplyTalentPool',label:'Bolsas de talento',help:'Te une a la bolsa de talento de la empresa cuando es opcional.',short:'Bolsas de talento'}
];
