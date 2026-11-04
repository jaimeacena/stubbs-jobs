"""Reusable form answers, recognised even when a question changes its words (04/11/2026).

Once answered, an answer holds: nothing asks to confirm it again. It is kept here only
when the profile and competencies cannot tell it. What they can tell is never stored
twice, what belongs to one offer is not reused, and a later different answer is flagged.
"""
import re

import skills
from form_rules import whole_years
from stubbs_jobs_core import digest, now

STRONG, POSSIBLE = .8, .5
STOPWORDS = set(('a al algun alguna are be can con cual cuales cuanta cuantas cuanto cuantos de del do el en es este esta for from has have how i if in is it la las lo los me mi many much o of on or para por que se si su sus te the this tienes to tu tus un una usted what which with you your').split())
SYNONYMS = {'ano': 'years', 'anos': 'years', 'year': 'years', 'yrs': 'years', 'experiencia': 'experience', 'experiencias': 'experience',
            'ingles': 'english', 'nivel': 'level', 'salario': 'salary', 'sueldo': 'salary', 'retribucion': 'salary', 'compensation': 'salary',
            'contrato': 'contract', 'remoto': 'remote', 'teletrabajo': 'remote', 'permiso': 'permit', 'authorization': 'permit', 'authorized': 'permit',
            'autorizacion': 'permit', 'visado': 'permit', 'visa': 'permit', 'sponsorship': 'permit', 'patrocinio': 'permit', 'trabajar': 'work', 'trabajo': 'work', 'working': 'work',
            'disponibilidad': 'availability', 'incorporacion': 'availability', 'incorporarte': 'availability', 'preaviso': 'notice', 'period': 'notice',
            'titulacion': 'degree', 'grado': 'degree', 'carrera': 'degree', 'certificacion': 'certification', 'certificado': 'certification',
            'ubicacion': 'location', 'ciudad': 'city', 'mudarte': 'relocate', 'traslado': 'relocate', 'relocation': 'relocate', 'viajar': 'travel', 'viajes': 'travel'}
# Tied to one company, form or moment: the old answer says nothing about the next one.
PER_OFFER = re.compile(r'consent|acepto\b|aceptas\b|aceptacion\b|terminos|condiciones|privacidad|privacy|terms|politica|policy|gdpr|rgpd|previa|ya has|has solicitado|applied before|'
                       r'previously applied|presentado tu perfil|por que|porque|why |motiv|carta|cover letter|referid|referred|como nos|how did you|conociste|'
                       r'te atrae|me atrae|ubicacion de la oferta|ubicacion elegida|lugar de la vacante|location are you applying|location chosen|modalidad elegida|'
                       r'origen de|fuente de|source|detalle de la fuente|que posicion|he trabajado antes en|has trabajado anteriormente|previously been employed|'
                       r'reconocimiento del aviso|remitentes seguros|if you could remove|talent pool|historial laboral|formacion incluida|prefijo telefonico|conservar datos')
SALARY = re.compile(r'salar|sueldo|retribu|compensation|pay expectation|banda')
CURRENT_SALARY = re.compile(r'(salario|sueldo|retribucion|remuneracion)( bruto| fijo| anual)* actual|current (gross |annual |base )*(salary|compensation|pay)')
DEMOGRAPHIC = re.compile(r'genero|gender|pronoun|pronombre|veteran|origen etnico|race|ethnic|encuesta|datos demograficos')
YEARS_WORDS = re.compile(r'anos|years|yrs|experiencia|experience')
YES_NO = re.compile(r'^(tienes|cuentas|has |have |do you|are you|eres|sabes)|\?$')


def tokens(question):
    text = re.sub(r'[^a-z0-9+#/ ]', ' ', skills.fold(question))
    return {SYNONYMS.get(word, word) for word in text.split() if word not in STOPWORDS}


def key(question):
    return ' '.join(sorted(tokens(question)))


def similarity(left, right):
    a, b = tokens(left), tokens(right)
    return len(a & b)/len(a | b) if a and b else 0


def listing(data):
    return data.get('app', {}).get('answerBank', [])


def _name_parts(data):
    from personalization import context
    words = str(context(data).get('name') or '').split()
    return words, (words[0] if words else None), (' '.join(words[1:]) or None)


LANGUAGE_NAMES = (('ingles', 'english'), ('espanol', 'spanish', 'castellano'), ('frances', 'french'), ('aleman', 'german'), ('italiano', 'italian'), ('portugues', 'portuguese'), ('catalan',))


def _language_answer(languages, text):
    """The one language a form asks about, or all of them when it asks in general."""
    if not languages:
        return None
    parts = [part.strip() for part in re.split(r',(?![^()]*\))', str(languages)) if part.strip()]
    asked = next((names for names in LANGUAGE_NAMES if any(name in text for name in names)), None)
    if not asked:
        return str(languages)
    match = next((part for part in parts if any(name in skills.fold(part) for name in asked)), None)
    return match or 'No consta ese idioma en tu perfil'


# Nationalities and countries of the 27 member states, folded, in Spanish and English.
EU_NATIONALITIES = re.compile(r'\b(espan|spain|spanish|frances|francia|france|french|aleman|alemania|german|italian|italia|italy|portugu|belg|holand|neerland|paises bajos|netherland|dutch|luxembur|irland|ireland|irish|austria|danes|danesa|dinamarca|denmark|danish|suec|sweden|swed|finland|finnish|finlandes|estoni|leton|latvi|litu|lithuan|polac|polonia|poland|polish|chec|czech|eslovac|slovak|eslovenia|esloven|sloven|hungar|rumani|romani|bulgar|croat|griego|griega|grecia|greece|greek|chipr|cyprus|cypriot|malt)')


def _eu_citizen(nationality):
    """Yes or no for «are you an EU citizen?», from the nationalities saved in Mi perfil."""
    nationality = skills.fold(nationality or '')
    if not nationality.strip():
        return None
    return bool(EU_NATIONALITIES.search(nationality))


def _university_degree(level):
    """Yes or no for «do you have a university degree?», from the highest level of education."""
    level = skills.fold(level or '')
    if not level.strip():
        return None
    # «Grado superior» is vocational training; «grado» alone is a university degree.
    if re.search(r'grado (medio|superior)|fp|ciclo|formacion profesional|bachillerato|eso|primaria|secundaria|sin estudios|high school|vocational', level):
        return False
    if re.search(r'grado|licenciatur|diplomatur|ingenier|master|doctor|phd|bachelor|mba|universit|degree', level):
        return True
    return None


# A question about doing something with a tool or topic («email marketing», «mobile development»,
# «have you worked in another country?») is not asking for the contact or place saved in Mi perfil.
TOPIC = re.compile(r'experienc|has trabajado|have you (?:ever )?(?:used|worked)|conocimient|knowledge|proficien|marketing|desarrollo|development|herramienta|\btools?\b|campana|campaign|estrategia|strategy|gestion de|management')
TOPIC_SENSITIVE_FIELDS = {'email', 'phone', 'linkedinUrl', 'custom_github_url', 'websiteUrl', 'currentCity', 'currentCountry', 'address', 'postalCode'}


def _lives_in(text, city, country):
    """Yes when the question names where the person lives; unknown when it names another place."""
    places = [skills.fold(part) for part in (city, country) if part]
    if not places:
        return None
    if any(re.search(r'\b' + re.escape(place) + r'\b', text) for place in places):
        return True
    if re.search(r'\b(ue|union europea|eu|european union|europa|europe)\b', text):
        return _eu_citizen(country)
    return None


def _profile_answer(data, text):
    """(field, value) when Mi perfil already answers the question; value None means it could but is empty."""
    from personalization import context
    profile, words = data.get('profile', {}), _name_parts(data)
    allowed = bool(profile.get('workPermitWithoutSponsorship') or profile.get('workAuthorizations'))
    city, country = profile.get('currentCity'), profile.get('currentCountry')
    place = ', '.join(part for part in (city, country) if part) or None
    # Going to a place is a decision about that place, not where the person lives or starts.
    if re.search(r'desplaz|acudir|presencial|viajar', text):
        return None
    topic = TOPIC.search(text)
    # From most to least specific: «nombre completo» before «nombre»; the current employer before any name.
    for pattern, field, value in (
        (r'empresa actual|current company|current employer', 'experience', None),
        (r'nombre completo|full name|nombre y apellidos', 'name', ' '.join(words[0]) or None),
        (r'apellido|last name|surname|family name', 'name', words[2]),
        (r'\bnombre\b(?!\s+del?\s+(?!pila))|first name|given name', 'name', words[1]),
        (r'correo|e-?mail', 'email', profile.get('email')),
        (r'telefono|phone|movil|mobile', 'phone', profile.get('phone')),
        (r'linkedin', 'linkedinUrl', profile.get('linkedinUrl')),
        (r'github', 'custom_github_url', profile.get('custom_github_url')),
        (r'portfolio|portafolio|sitio web|website', 'websiteUrl', profile.get('websiteUrl')),
        (r'patrocinio|sponsorship|visa\b|visado', 'workAuthorizations', False if allowed else None),
        (r'permiso (de|para) trabaj|right to work|work permit|autorizado para trabajar|authorized to work|permit', 'workAuthorizations', True if allowed else None),
        (r'ciudadan[oa]s? (de la )?(ue|union europea)|ciudadania (de la )?(ue|union europea|europea)|eu citizen|citizen of the (eu|european union)|european union citizen', 'custom_nationality', _eu_citizen(profile.get('custom_nationality'))),
        (r'nacionalidad|nationality', 'custom_nationality', profile.get('custom_nationality')),
        (r'nivel (de )?(estudios|educativo|de formacion|academico)|level of education|education level|highest (level of )?(education|degree)|estudios (maximos|mas altos)', 'custom_education_level', profile.get('custom_education_level')),
        (r'(tienes|dispones|cuentas con|posees|dispongo de|tengo|have) (de )?(una |un |a )?(titulacion|titulo|grado|carrera) universitari|university degree|(have|hold) a (bachelor|degree)', 'custom_education_level', _university_degree(profile.get('custom_education_level'))),
        (r'fecha de nacimiento|date of birth|birth date', 'custom_birth_date', profile.get('custom_birth_date')),
        (r'codigo postal|postal code|\bzip\b', 'postalCode', profile.get('postalCode')),
        (r'direccion|\baddress\b', 'address', profile.get('address')),
        (r'resides? en|vives en|living in|based in|reside in|live in', 'currentCountry', _lives_in(text, city, country)),
        (r'donde vives|lugar desde|ubicacion|location|zona horaria|time ?zone', 'currentCity', place),
        (r'\bciudad\b|\bcity\b', 'currentCity', city),
        (r'\bpais\b|country', 'currentCountry', country),
        (r'preaviso|notice period|disponibilidad(?! (?:para|de) (?!incorpor|empezar|comenzar))|incorporaci|cuando\b.*\b(?:incorpor|empezar|comenzar)|start date|availability|when can you start', 'noticeDays', profile.get('noticeDays')),
        (r'ingles|english|frances|french|espanol|spanish|aleman|german|italiano|italian|portugues|portuguese|idioma|language|bilingue|bilingual', 'languages', _language_answer(context(data).get('languages'), text)),
        (r'mudar|relocat|traslad', 'custom_open_to_relocation', profile.get('custom_open_to_relocation')),
        (r'carnet|permiso de conducir|driving|driver', 'custom_driving_license', profile.get('custom_driving_license')),
        (r'vehiculo|vehicle|\bcoche\b|\bcar\b', 'custom_own_vehicle', profile.get('custom_own_vehicle')),
        (r'alta como autonomo|self.?employed', 'custom_self_employed', profile.get('custom_self_employed')),
        (r'discapacidad|disability', 'custom_disability', profile.get('custom_disability')),
    ):
        if not re.search(pattern, text):
            continue
        if topic and field in TOPIC_SENSITIVE_FIELDS:
            continue
        # «Programming languages» are skills, not the languages a person speaks.
        if field == 'languages' and re.search(r'programaci|programming|coding|lenguajes? de|query language|\bsql\b', text):
            continue
        # «Availability to work weekends» is about a schedule, not the start date.
        if field == 'noticeDays' and re.search(r'availability (?:to|for) (?!start)|fin(?:es)? de semana|weekend|turno|shift|horario', text):
            continue
        return field, value
    return None


def _tool_in_question(data, text):
    import requirement_match
    if not YEARS_WORDS.search(text) and not re.search(r'tienes|cuentas|uso de|have you|do you have|conocimientos', text):
        return None
    known = _skill_in_question(data, text)
    if known:
        return known['name']
    terms = sorted(((alias, name) for name, aliases in requirement_match.VOCABULARY.items() for alias in aliases), key=lambda term: -len(term[0]))
    # «Azure AI Foundry» says nothing about Azure: the name must end where the question does.
    return next((name for alias, name in terms if re.search(r'(?<![\w/+#-])'+re.escape(skills.fold(alias))+r'(?=\s*(?:$|[?.,;:)]|para\b|en\b|for\b|in\b))', text)), None)


def classify_text(question, data=None):
    """profile, per-offer, salary, skill, raw (a technical key instead of a question) or general."""
    text = skills.fold(question)
    if re.fullmatch(r'custom_\w+', text):
        return 'raw'
    if PER_OFFER.search(text):
        return 'per-offer'
    if SALARY.search(text) or CURRENT_SALARY.search(text):
        return 'salary'
    if DEMOGRAPHIC.search(text):
        return 'profile'
    if data is not None and _tool_in_question(data, text):
        return 'skill'
    if _profile_answer(data or {}, text):
        return 'profile'
    return 'general'


def clean_question(question, company=None):
    """An advert's company name says nothing about the question: «Nombre para Acme» is «Nombre»."""
    text = ' '.join(str(question or '').split())
    if company:
        name = re.escape(str(company).strip())
        text = re.sub(rf'\s*\(\s*{name}\s*\)', '', text, flags=re.I)
        text = re.sub(rf'\s+(?:para|en|de|at|for|in)\s+{name}\b', '', text, flags=re.I)
        text = re.sub(rf'\s+{name}\s*(\?)?$', r'\1', text, flags=re.I)
    return text.strip(' -–:')


def _learn_skill(data, question, value):
    """A tool asked in a form becomes one competency, the only source of its years."""
    name = _tool_in_question(data, skills.fold(question))
    if not name or skills.find(data, name):
        return False
    years = None
    if value is False or (isinstance(value, str) and re.match(r'\s*no\b', skills.fold(value))):
        years = 0
    elif type(value) in (int, float):
        years = value
    elif isinstance(value, str) and re.fullmatch(r'\s*\d+(?:[.,]\d+)?\s*', value):
        years = float(value.replace(',', '.'))
    data['app'].setdefault('skills', []).append({'id': 'skill-'+digest(skills.fold(name))[:12], 'name': name, 'aliases': [], 'years': years, 'level': None, 'kind': 'professional',
                                                 'lastUsed': None, 'usedAt': None, 'status': 'confirmed' if years is not None else 'proposed', 'updatedAt': now(), 'source': 'send'})
    return True


def _skill_in_question(data, question):
    text = skills.fold(question)
    # Longest name first: «Power BI» wins over a shorter alias inside the same question.
    candidates = sorted(((name, skill) for skill in skills.listing(data) for name in skills.names(skill)), key=lambda item: -len(item[0]))
    return next((skill for name, skill in candidates if skills.mentions(text, name)), None)


def lookup(data, question, case=None, search_profile_id=None):
    """How to answer one form question: use = answer, suggest (review it) or ask (no invented data)."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError('Escribe la pregunta del formulario')
    text, profile = skills.fold(question), data.get('profile', {})
    if PER_OFFER.search(text):
        return {'use': 'ask', 'source': 'per-offer', 'value': None, 'note': 'Es propia de esta oferta: compruébala en el formulario y aplica los permisos guardados.'}
    if CURRENT_SALARY.search(text):
        import app_workflow
        current = app_workflow.current_salary(profile)
        amount, currency = current['currentSalary'], current['currentSalaryCurrency']
        if amount is None or not currency:
            return {'use': 'ask', 'source': 'current-salary', 'value': amount, 'currency': currency or None,
                    'note': 'Falta el salario actual o su moneda en Datos personales. No lo sustituyas por el salario que pides.'}
        return {'use': 'answer', 'source': 'profile', 'field': 'currentSalary', 'value': amount, 'currency': currency,
                'note': 'Dato de Mi perfil, bruto anual. Si el formulario pide otra moneda o periodo, pregunta a la persona.'}
    if SALARY.search(text):
        import search_profiles
        salary = search_profiles.offer_form_salary(data, case) if case else search_profiles.form_salary(data, search_profile_id)
        return {'use': 'answer', 'source': 'salary', 'value': salary['salaryExpectationFixed'], 'currency': salary['salaryCurrency'],
                'note': 'Si pide otra moneda o periodo, usa salary-answer. El mínimo interno nunca se responde.'}
    if DEMOGRAPHIC.search(text):
        import app_workflow
        mode = app_workflow.survey_mode(profile.get('demographicSurveyParticipation'))
        return {'use': 'answer' if mode == 'decline' else 'ask', 'source': 'demographic', 'value': 'Prefiero no responder' if mode == 'decline' else None,
                'note': 'Sigue tu decisión sobre encuestas demográficas; usa la opción equivalente del formulario.'}
    found = _skill_in_question(data, question)
    if not found:
        known = _profile_answer(data, text)
        if known and known[1] not in (None, ''):
            return {'use': 'answer', 'source': 'profile', 'field': known[0], 'value': known[1], 'note': 'Dato de Mi perfil. Responde en el idioma del formulario y con sus opciones.'}
    if found and YEARS_WORDS.search(text):
        years = found.get('years')
        if found.get('status') == 'confirmed' and years is not None:
            return {'use': 'answer', 'source': 'skill', 'skill': found['name'], 'value': whole_years(years), 'exactYears': years,
                    'kind': found.get('kind'), 'note': 'Competencia confirmada. Con varias opciones de rango, elige la que contenga este valor.'}
        return {'use': 'suggest', 'source': 'skill', 'skill': found['name'], 'value': years, 'note': 'Competencia sin confirmar: pregunta a la persona o deduce solo de su experiencia.'}
    best, score = None, 0
    for entry in listing(data):
        for candidate in (entry['question'], *entry.get('aliases', [])):
            value = similarity(question, candidate)
            if value > score:
                best, score = entry, value
    if best and score >= POSSIBLE:
        trusted = score >= STRONG and not best.get('conflict')
        return {'use': 'answer' if trusted else 'suggest', 'source': 'bank', 'value': best['value'], 'question': best['question'],
                'similarity': round(score, 2), 'note': 'Ya lo respondiste: reutilízalo en el idioma del formulario.' if trusted else 'Respuesta parecida o con una diferencia posterior: comprueba que sirve aquí.'}
    if not found and YEARS_WORDS.search(text):
        note = 'No consta como competencia. Revisa la experiencia; si tampoco consta, no afirmes que la tienes.'
    else:
        note = 'Sin respuesta guardada: deduce solo de datos confirmados o pregunta a la persona.'
    return {'use': 'ask', 'source': 'none', 'value': None, 'note': note}


def _entry(data, question):
    wanted = key(question)
    return next((entry for entry in listing(data) if entry['key'] == wanted), None)


def _add_used(data, question, value, offer):
    """Remember an answer already given, without overriding what the person confirmed."""
    kind = classify_text(question, data)
    if kind == 'skill':
        return _learn_skill(data, question, value)
    if kind != 'general' or value in (None, '') or key(question) in data['app'].get('answerBankRemoved', []):
        return False
    bank = data['app'].setdefault('answerBank', [])
    entry = _entry(data, question)
    if entry is None:
        bank.append({'id': 'answer-'+digest(key(question))[:12], 'key': key(question), 'question': question.strip(), 'aliases': [], 'value': value,
                     'status': 'used', 'usedIn': [offer], 'updatedAt': now()})
        return True
    changed = offer not in entry.setdefault('usedIn', [])
    if changed:
        entry['usedIn'].append(offer)
    if entry['value'] != value:
        changed = changed or not entry.get('conflict')
        entry['conflict'] = True
        entry['laterValue'] = value
    return changed


def harvest(data, package):
    """Keep the particular answers of a confirmed send for the next forms."""
    payload = package.get('payload') or {}
    questions = {q['key']: q for q in payload.get('questions') or [] if q.get('scope') == 'opportunity'}
    count = 0
    for name in payload.get('formAnswerKeys') or []:
        if name in questions and _add_used(data, clean_question(questions[name].get('label', ''), payload.get('company')), (payload.get('answers') or {}).get(name), payload.get('opportunityId')):
            count += 1
    return count


def harvest_all(data):
    """Rebuild suggestions from the packages of sends already confirmed; safe to repeat."""
    packages = {p['id']: p for p in data.get('app', {}).get('packages', [])}
    return sum(harvest(data, packages[e['packageId']]) for e in data.get('events', []) if e.get('type') == 'sent' and e.get('packageId') in packages)


def tidy(data):
    """Keep only what the profile cannot tell; competencies learn what they should hold."""
    kept, counts = [], {'general': 0, 'skill': 0, 'profile': 0, 'per-offer': 0, 'salary': 0, 'raw': 0}
    for entry in list(listing(data)):
        kind = classify_text(entry['question'], data)
        counts[kind] += 1
        if kind == 'general':
            kept.append(entry)
        elif kind == 'skill':
            _learn_skill(data, entry['question'], entry.get('value'))
    data['app']['answerBank'] = kept
    return counts


def view(data):
    rows = [{**entry, 'uses': len(entry.get('usedIn') or [])} for entry in listing(data)]
    rows.sort(key=lambda row: (not row.get('conflict'), skills.fold(row['question'])))
    return rows


def handle(data, op):
    kind = op['kind']
    if kind not in ('ui-answer-save', 'ui-answer-remove', 'ui-answer-harvest', 'ui-answer-tidy', 'ui-answer-import'):
        return False
    import app_workflow as workflow
    app = workflow.state(data)
    actor, proof = op.get('actor', 'Agente'), op.get('proof')
    by_person = workflow.chosen_by_person(actor)
    if not by_person and (not isinstance(proof, str) or not 10 <= len(proof.strip()) <= 2000):
        raise ValueError('Indica las palabras de la persona o de dónde sale esta respuesta')
    if kind == 'ui-answer-harvest':
        count = harvest_all(data)
        workflow.record(data, 'Respuestas anteriores recuperadas', actor=actor, detail=f'{count} cambios desde solicitudes confirmadas. {proof or ""}'.strip())
        return True
    if kind == 'ui-answer-tidy':
        counts = tidy(data)
        workflow.record(data, 'Respuestas guardadas simplificadas', actor=actor, detail=f'{counts} {proof or ""}'.strip())
        return True
    if kind == 'ui-answer-import':
        # One list unifies questions: other wordings and languages become its aliases.
        entries = op.get('entries')
        if not isinstance(entries, list) or len(entries) > 500:
            raise ValueError('Indica la lista de respuestas')
        result = []
        for item in entries:
            question, value, aliases = item.get('question'), item.get('value'), item.get('aliases', [])
            if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500 or classify_text(question) in ('per-offer', 'raw'):
                raise ValueError('Esa pregunta no se guarda como respuesta general: '+str(question)[:80])
            if type(value) not in (str, int, float, bool) or (isinstance(value, str) and not 1 <= len(value.strip()) <= 5000):
                raise ValueError('Falta la respuesta de: '+question[:80])
            if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
                raise ValueError('Revisa los otros textos de: '+question[:80])
            if any(entry['key'] == key(question) for entry in result):
                raise ValueError('Pregunta repetida: '+question[:80])
            result.append({'id': 'answer-'+digest(key(question))[:12], 'key': key(question), 'question': question.strip(), 'aliases': aliases, 'value': value,
                           'status': 'confirmed', 'usedIn': [], 'updatedAt': now()})
        app['answerBank'] = result
        workflow.record(data, 'Respuestas guardadas unificadas', actor=actor, detail=f'{len(result)} respuestas. {proof or ""}'.strip())
        return True
    bank = app.setdefault('answerBank', [])
    current = next((entry for entry in bank if entry['id'] == op.get('id')), None)
    if op.get('id') and current is None:
        raise ValueError('Esa respuesta ya no existe; actualiza el estado')
    if 'expected' in op:
        workflow.expect(current and {k: current.get(k) for k in ('value', 'status')}, op['expected'])
    if kind == 'ui-answer-remove':
        if current is None:
            raise ValueError('Indica la respuesta que quieres quitar')
        bank.remove(current)
        removed = app.setdefault('answerBankRemoved', [])
        if current['key'] not in removed:
            removed.append(current['key'])
        workflow.record(data, 'Respuesta guardada retirada', actor=actor, detail=current['question'])
        return True
    question, value = op.get('question', current['question'] if current else None), op.get('value')
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
        raise ValueError('Escribe la pregunta')
    kind_of_question = classify_text(question)
    if kind_of_question in ('per-offer', 'salary', 'raw'):
        raise ValueError('Esta pregunta depende de cada oferta o de tu salario para formularios; no se guarda como respuesta general')
    if type(value) not in (str, int, float, bool) or (isinstance(value, str) and not 1 <= len(value.strip()) <= 5000):
        raise ValueError('Escribe la respuesta')
    other = _entry(data, question)
    if other is not None and other is not current:
        raise ValueError('Ya hay una respuesta guardada para esa pregunta: edítala')
    record = {'id': current['id'] if current else 'answer-'+digest(key(question))[:12], 'key': key(question), 'question': question.strip(),
              'aliases': (current or {}).get('aliases', []), 'value': value.strip() if isinstance(value, str) else value, 'status': 'confirmed',
              'usedIn': (current or {}).get('usedIn', []), 'updatedAt': now()}
    if proof:
        record['proof'] = proof.strip()
    if current:
        bank[bank.index(current)] = record
    else:
        bank.append(record)
    removed = app.get('answerBankRemoved', [])
    if record['key'] in removed:
        removed.remove(record['key'])
    workflow.record(data, 'Respuesta guardada: '+record['question'][:80], actor=actor, detail=proof or 'Confirmada desde Mi perfil.')
    return True
