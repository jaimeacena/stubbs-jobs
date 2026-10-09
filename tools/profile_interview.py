"""Progressive interview: confirm search essentials; preserve undecided optional data."""
import copy

from stubbs_jobs_core import digest, now


# Related fields share a conversation, not an extra screen or a question per key.
FIELDS = (
    ('targetRoles', 'Puestos que buscas', 'busqueda', 'text'),
    ('location', 'Zona de búsqueda', 'busqueda', 'text'),
    ('regions', 'Otras zonas, si las hay', 'busqueda', 'text'),
    ('workMode', 'Modalidad de trabajo', 'busqueda', 'text'),
    ('onsiteLocations', 'Zonas donde aceptas presencial o híbrido (opcional)', 'busqueda', 'text'),
    ('searchPriorities', 'Horario que prefieres', 'busqueda', 'text'),
    ('searchNotes', 'Indicaciones adicionales de búsqueda (opcional)', 'busqueda', 'text'),
    ('name', 'Nombre y apellidos', 'sobre_mi', 'text'),
    ('email', 'Email para solicitudes', 'sobre_mi', 'text'),
    ('phone', 'Teléfono con prefijo internacional', 'sobre_mi', 'text'),
    ('currentCountry', 'País de residencia', 'sobre_mi', 'text'),
    ('postalCode', 'Código postal', 'sobre_mi', 'text'),
    ('address', 'Dirección (opcional)', 'sobre_mi', 'text'),
    ('linkedinUrl', 'LinkedIn (opcional)', 'sobre_mi', 'text'),
    ('websiteUrl', 'Web o portfolio (opcional)', 'sobre_mi', 'text'),
    ('gender', 'Género (opcional)', 'sobre_mi', 'text'),
    ('demographicSurveyParticipation', 'Participar en encuestas demográficas (opcional)', 'sobre_mi', 'boolean'),
    ('experience', 'Experiencia, formación y proyectos', 'sobre_mi', 'text'),
    ('languages', 'Idiomas y nivel', 'sobre_mi', 'text'),
    ('currentCity', 'Ciudad actual', 'sobre_mi', 'text'),
    ('workAuthorizations', 'Países o zonas con permiso de trabajo sin patrocinio', 'sobre_mi', 'multiselect'),
    ('noticeDays', 'Preaviso (laborable, natural u otra especificación)', 'sobre_mi', 'text'),
    ('contract', 'Tipo de contrato', 'condiciones', 'text'),
    ('minimumFixed', 'Mínimo fijo bruto anual', 'condiciones', 'number'),
    ('salaryExpectationFixed', 'Salario deseado para formularios', 'condiciones', 'number'),
    ('currency', 'Moneda de los salarios', 'condiciones', 'text'),
    ('maxTrips', 'Máximo de viajes al mes', 'condiciones', 'number'),
    ('keywords', 'Palabras clave útiles', 'fuentes', 'text'),
    ('sourceUrls', 'Webs exclusivas de búsqueda (opcional)', 'fuentes', 'text'),
    ('platforms', 'Plataformas preferidas', 'fuentes', 'text'),
    ('previousApplications', 'Empresas a evitar', 'antecedentes', 'text'),
    ('cv', 'Currículums que quieres aportar', 'curriculums', 'documents'),
)
GUIDANCE = {
    'busqueda': 'Aclara puestos, zona, modalidad y prioridades; distingue límites firmes de preferencias.',
    'sobre_mi': 'Propón lo que conste en el CV para confirmarlo; separa empleo, formación y proyectos. Trata nombre, email, teléfono con prefijo, residencia, código postal, dirección y enlaces; son opcionales y pueden quedar en blanco por decisión expresa. No reutilices silenciosamente datos del CV en lugar de los guardados en Mi perfil. Confirma cada destino con permiso sin patrocinio; no amplíes un permiso nacional a toda Europa. Preaviso admite días laborables/naturales, semanas o texto. No supongas ciudad, permiso ni nivel de idioma.',
    'condiciones': 'Distingue mínimo fijo y salario deseado, siempre bruto anual con moneda. Cero viajes o días es una respuesta, no un vacío.',
    'fuentes': 'Propón palabras clave basadas en lo confirmado. Puede dejar que la IA elija fuentes: confirma qué datos deja en blanco.',
    'antecedentes': 'Distingue candidaturas previas y empresas que quiere evitar. Un campo vacío no significa que nunca haya solicitado empleo.',
    'curriculums': 'CV opcional: confirma los documentos aportados o la decisión de continuar sin CV.',
    'otros': 'Trata también las preguntas generales que ya figuren en Mi perfil, conservando su significado.',
}
ESSENTIAL = {'targetRoles','location','workMode','contract','minimumFixed','maxTrips','experience','cv'}


def fields(data=None):
    result = {key: {'key': key, 'label': label, 'group': group, 'type': kind}
              for key, label, group, kind in FIELDS}
    if data is not None:
        import app_context
        import view_cache
        # Catalog recovery may populate legacy metadata. A query must stay pure,
        # and the temporary copy must not share an id-based projection cache.
        with view_cache.snapshot():
            definitions = app_context.definitions(copy.deepcopy(data))
        for key, definition in definitions.items():
            if key.startswith('custom_') and definition.get('scope') == 'global':
                result[key] = {**definition, 'group': 'otros'}
    return result


def value(data, draft, field):
    key = field['key']
    if key == 'cv':
        return sorted(({k: document.get(k) for k in ('id', 'name', 'path', 'hash')}
                       for document in data.get('app', {}).get('cvLibrary', [])),
                      key=lambda document: (str(document['id']), str(document['path'])))
    answer = draft.get(key)
    if field['type'] == 'text':
        if key=='noticeDays' and type(answer) is int:return str(answer)
        return answer.strip() if isinstance(answer, str) else None if key.startswith('custom_') or key == 'currentCity' else ''
    return answer


def has_value(answer):
    return answer is not None and answer != '' and answer != []


def fingerprint(data, draft, field):
    answer = value(data, draft, field)
    meaning = {}
    # A fixed amount in a different currency or a permit for a different
    # destination is a different answer, even when its stored value is unchanged.
    if has_value(answer):
        if field['key'] in ('minimumFixed', 'salaryExpectationFixed'):
            meaning = {'currency': draft.get('currency', '').strip()}
        elif field['key'] == 'workPermitWithoutSponsorship':
            meaning = {key: draft.get(key, '').strip() for key in ('location', 'regions')}
    return digest(['profile-interview-v1', field, answer, meaning])


def decisions(data, draft, previous, updates):
    """Merge only explicitly supplied decisions; never infer consent from defaults."""
    catalog = fields(data)
    if not isinstance(updates, dict) or set(updates) - set(catalog):
        raise ValueError('Revisa los campos tratados en la entrevista inicial')
    result = copy.deepcopy(previous)
    for key, decision in updates.items():
        if not isinstance(decision, dict) or set(decision) - {'status', 'proof'}:
            raise ValueError('Cada campo necesita una decisión y la respuesta de la persona')
        status, proof = decision.get('status'), decision.get('proof')
        if status not in ('provided', 'blank') or not isinstance(proof, str) or not 1 <= len(proof.strip()) <= 2000:
            raise ValueError('Conserva la respuesta o decisión expresa de dejar el campo en blanco')
        present = has_value(value(data, draft, catalog[key]))
        if present != (status == 'provided'):
            raise ValueError('La decisión no coincide con el dato de «'+catalog[key]['label']+'»')
        result[key] = {'status': status, 'proof': proof.strip(),
                       'fingerprint': fingerprint(data, draft, catalog[key]), 'at': now()}
    return result


def coverage(data, draft, saved):
    catalog = fields(data)
    required=set(ESSENTIAL)
    if any(has_value(draft.get(key)) for key in ('minimumFixed','salaryExpectationFixed')):required.add('currency')
    # Supplied optional facts also need confirmation; absent ones can wait.
    required.update(key for key,field in catalog.items() if has_value(value(data,draft,field)))
    result = {'total': len(catalog), 'provided': 0, 'blank': 0, 'pending': 0, 'requiredPending':0,
              'requiredTotal':len(required), 'fields': [], 'nextQuestions': []}
    pending_groups = {}
    for key, field in catalog.items():
        decision = saved.get(key, {})
        current = (decision.get('status') in ('provided', 'blank') and bool(decision.get('proof')) and
                   decision.get('fingerprint') == fingerprint(data, draft, field) and
                   has_value(value(data, draft, field)) == (decision['status'] == 'provided'))
        status = decision['status'] if current else 'pending'
        result[status] += 1
        result['fields'].append({**field, 'status': status,'requiredNow':key in required})
        if status == 'pending' and key in required:
            result['requiredPending']+=1
            pending_groups.setdefault(field['group'], []).append({'key': key, 'label': field['label']})
    result['complete'] = result['requiredPending'] == 0
    result['allComplete'] = result['pending'] == 0
    result['optionalPending'] = result['pending']-result['requiredPending']
    # This guides the external AI's next turn; it does not generate assumptions,
    # contact anyone, or start the conversation on behalf of the person.
    result['nextQuestions'] = [{'group': group, 'fields': pending, 'guidance': GUIDANCE[group]}
                               for group, pending in pending_groups.items()]
    return result


def require_complete(data, draft, saved):
    result = coverage(data, draft, saved)
    if not result['complete']:
        labels = [field['label'] for field in result['fields'] if field['status'] == 'pending' and field['requiredNow']]
        raise ValueError('Todavía quedan campos por tratar: '+', '.join(labels)+'. Pregunta por ellos o conserva la decisión expresa de dejarlos en blanco.')
    if any(draft.get(key) is not None for key in ('minimumFixed', 'salaryExpectationFixed')) and not draft.get('currency', '').strip():
        raise ValueError('Confirma la moneda de los importes salariales antes de guardar el perfil')
    return result
