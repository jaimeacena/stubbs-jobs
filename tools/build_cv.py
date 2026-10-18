"""One-page CV in PDF adapted to one offer, built only from the confirmed profile.

The agent writes an adaptation (summary, order of roles, bullets chosen from the
existing ones, highlighted technologies) and this module checks every fact against
the confirmed experience before rendering. See «build-cv» in docs/operations.md.

Text values are either a literal string that appears in the profile or
{"from": <literal profile text>, "text": <condensed or translated text>}. A
rendered text may not add numbers or proper names (tools, companies, titles,
places) absent from its source; translated proper names are declared in
"glossary" and must map to a word of that source.
"""
import io
import re
import unicodedata
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from stubbs_jobs_core import ROOT, digest

MAX_BULLETS = 6
MIN_FRAGMENT = 12
MIN_REASON = 20
LANGUAGES = ('es', 'en')
SPEC_KEYS = {'language', 'cvReason', 'headline', 'summary', 'highlights', 'experience', 'projects',
             'education', 'certifications', 'languages', 'glossary'}
ROLE_KEYS = {'title', 'company', 'dates', 'description', 'bullets'}
PROJECT_KEYS = {'name', 'text'}
LABELS = {
    'es': {'summary': 'Perfil profesional', 'highlights': 'Tecnologías', 'experience': 'Experiencia profesional',
           'projects': 'Proyectos', 'education': 'Formación', 'certifications': 'Certificaciones',
           'languages': 'Idiomas'},
    'en': {'summary': 'Professional summary', 'highlights': 'Key skills', 'experience': 'Professional experience',
           'projects': 'Projects', 'education': 'Education', 'certifications': 'Certifications',
           'languages': 'Languages'},
}
HIDDEN_HEADINGS = ('proyectos ocultos', 'hidden projects')
HIDDEN_MARKS = ('(oculto)', '[oculto]', '(hidden)', '[hidden]')
# Words that a translation may introduce without a source: months and «present».
NEUTRAL = {'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
           'november', 'december', 'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct',
           'nov', 'dec', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
           'septiembre', 'setiembre', 'octubre', 'noviembre', 'diciembre', 'ene', 'abr', 'ago', 'dic',
           'present', 'today', 'now', 'actualidad', 'presente', 'hoy', 'i'}
NUMBER_WORDS = {'one': 1, 'uno': 1, 'una': 1, 'two': 2, 'dos': 2, 'twice': 2, 'double': 2, 'doble': 2,
                'three': 3, 'tres': 3, 'four': 4, 'cuatro': 4, 'five': 5, 'cinco': 5, 'six': 6, 'seis': 6,
                'seven': 7, 'siete': 7, 'eight': 8, 'ocho': 8, 'nine': 9, 'nueve': 9, 'ten': 10, 'diez': 10,
                'eleven': 11, 'once': 11, 'twelve': 12, 'doce': 12, 'dozen': 12, 'docena': 12,
                'fifteen': 15, 'quince': 15, 'twenty': 20, 'veinte': 20, 'thirty': 30, 'treinta': 30,
                'fifty': 50, 'cincuenta': 50, 'hundred': 100, 'cien': 100, 'thousand': 1000, 'mil': 1000}
TOKEN = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ][0-9A-Za-zÀ-ÖØ-öø-ÿ+#'’./\-]*")
BOUNDARY = set('.:;!?·|•–—\n')


def fold(text):
    """Accent-insensitive, case-insensitive text with uniform dashes and spaces."""
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r'[‐-―−]', '-', text).replace('’', "'")
    return re.sub(r'\s+', ' ', text).strip()


def contains(haystack, needle):
    """Word-bounded search of folded text."""
    needle = fold(needle)
    return bool(needle) and re.search(r'(?<![0-9a-z])' + re.escape(needle) + r'(?![0-9a-z])', fold(haystack)) is not None


def numbers(text, reference=False):
    found = {int(group) for group in re.findall(r'\d+', text)}
    for word in re.findall(r'[a-z]+', fold(text)):
        if word in NUMBER_WORDS:found.add(NUMBER_WORDS[word])
        elif reference and word == 'un':found.add(1)
    return found


def distinctive(text, names=False):
    """Proper names and acronyms: tokens with inner capitals, or capitalised mid-sentence.
    In name fields (titles, companies, technologies, projects) every capitalised token counts."""
    result = []
    for match in TOKEN.finditer(text):
        token = match.group().rstrip('.-/\'’')
        if not token or token.isdigit() or not any(c.isalpha() for c in token):continue
        before = text[:match.start()].rstrip(' \t"«“(')
        start = not before or before[-1] in BOUNDARY or before.endswith(' -')
        inner = any(c.isupper() for c in token[1:])
        if inner or (token[0].isupper() and (names or not start)):result.append(token)
    return result


def unsupported(text, reference, glossary, names=False):
    """Numbers and proper names of text that its reference does not contain."""
    missing = [str(n) for n in sorted(numbers(text) - numbers(reference, reference=True))]
    for token in distinctive(text, names):
        if fold(token) in NEUTRAL or contains(reference, token):continue
        source = glossary.get(token) or glossary.get(fold(token))
        if source and contains(reference, source):continue
        missing.append(token)
    return list(dict.fromkeys(missing))


class Profile:
    """Confirmed experience text, without hidden projects."""

    def __init__(self, text, extra_hidden=()):
        lines, hidden, in_hidden, listed = [], list(extra_hidden), False, 0
        for raw in text.splitlines():
            line = raw.strip()
            heading = fold(line).lstrip('#').strip()
            if heading.startswith(HIDDEN_HEADINGS):
                in_hidden, listed = True, 0
                continue
            # The hidden list ends at the next Markdown heading or the blank line after its items.
            if in_hidden and (line.startswith('#') or not line and listed):
                in_hidden = False
            if in_hidden and not line:
                continue
            if in_hidden or any(mark in fold(line) for mark in HIDDEN_MARKS):
                listed += 1
                name = re.split(r'\s[–—-]\s|:|\(|\[', line.lstrip('-•* ').strip(), maxsplit=1)[0].strip()
                if name:hidden.append(name)
                continue
            lines.append(line)
        self.lines = lines
        self.text = '\n'.join(lines)
        self.hidden = [name for name in dict.fromkeys(hidden) if len(fold(name)) >= 3]

    def block(self, title, company):
        """Lines of the role whose header names both title and company."""
        for index, line in enumerate(self.lines):
            if contains(line, title) and contains(line, company):
                if line.startswith(('-', '•', '*')):return [line]
                end = index + 1
                while end < len(self.lines) and self.lines[end]:end += 1
                return self.lines[index:end]
        return None


def hidden_from_private(root):
    """Hidden projects listed in private/profile.md (section «Proyectos ocultos»)."""
    path = Path(root) / 'private/profile.md'
    if not path.is_file():return []
    return Profile(path.read_text(encoding='utf-8')).hidden


class Checker:
    def __init__(self, profile, glossary):
        self.profile = profile
        self.glossary = glossary
        self.issues = []

    def problem(self, where, message):
        self.issues.append(f'{where}: {message}')

    def value(self, item, where, scope=None, fragment=False, names=False):
        """Rendered text of a literal or {from,text} value checked against scope."""
        scope = self.profile.text if scope is None else scope
        if isinstance(item, str):
            source, text = item, item
        elif isinstance(item, dict) and set(item) <= {'from', 'text'} and isinstance(item.get('from'), str) \
                and isinstance(item.get('text', item['from']), str):
            source, text = item['from'], item.get('text', item['from'])
        else:
            self.problem(where, 'usa un texto o {"from": texto del perfil, "text": versión adaptada}')
            return ''
        source, text = source.strip(), re.sub(r'\s+', ' ', text).strip()
        if not source or not text:
            self.problem(where, 'el texto está vacío')
            return ''
        if fragment and len(fold(source)) < MIN_FRAGMENT:
            self.problem(where, f'«{source}» es demasiado corto para identificar una viñeta del perfil')
        if fold(source) not in fold(scope):
            self.problem(where, f'«{source}» no consta en el perfil confirmado' + (' para este puesto' if scope is not self.profile.text else ''))
            return text
        extra = unsupported(text, source, self.glossary, names)
        if extra:
            self.problem(where, 'añade datos que no constan en «' + source + '»: ' + ', '.join(extra))
        return text

    def free(self, text, where):
        """Agent-written text (summary, headline): every number and name must be in the profile."""
        if not isinstance(text, str) or not text.strip():
            self.problem(where, 'falta el texto')
            return ''
        text = re.sub(r'\s+', ' ', text).strip()
        extra = unsupported(text, self.profile.text, self.glossary)
        if extra:
            self.problem(where, 'menciona datos que no constan en el perfil: ' + ', '.join(extra))
        return text

    def hidden(self, text, where):
        for name in self.profile.hidden:
            if contains(text, name):
                self.problem(where, f'menciona el proyecto oculto «{name}»')


def validate(spec, profile_text, extra_hidden=()):
    """Return the CV content checked against the profile, or raise ValueError with every issue."""
    if not isinstance(spec, dict):raise ValueError('La adaptación debe ser un objeto JSON')
    unknown = set(spec) - SPEC_KEYS
    if unknown:raise ValueError('Campos de adaptación no admitidos: ' + ', '.join(sorted(unknown)))
    if not profile_text.strip():raise ValueError('No hay experiencia confirmada en el perfil; no se puede preparar un CV sin inventar')
    language = spec.get('language')
    if language not in LANGUAGES:raise ValueError('Indica language: es o en')
    glossary = spec.get('glossary', {})
    if not isinstance(glossary, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in glossary.items()):
        raise ValueError('glossary relaciona cada término traducido con su palabra del perfil')
    glossary = {**glossary, **{fold(k): v for k, v in glossary.items()}}
    profile = Profile(profile_text, extra_hidden)
    check = Checker(profile, glossary)
    reason = spec.get('cvReason')
    if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
        check.problem('cvReason', f'explica en al menos {MIN_REASON} caracteres qué se adaptó a esta oferta')
    content = {'language': language, 'cvReason': (reason or '').strip() if isinstance(reason, str) else ''}
    if spec.get('headline') is not None:content['headline'] = check.free(spec['headline'], 'headline')
    content['summary'] = check.free(spec.get('summary'), 'summary')
    highlights = spec.get('highlights', [])
    if not isinstance(highlights, list) or len(highlights) > 16:
        check.problem('highlights', 'indica una lista de hasta 16 tecnologías del perfil')
        highlights = []
    content['highlights'] = []
    for index, item in enumerate(highlights, 1):
        source = item if isinstance(item, str) else item.get('from') if isinstance(item, dict) else None
        if isinstance(source, str) and not contains(profile.text, source):
            check.problem(f'highlights {index}', f'«{source}» no consta en el perfil: no se añaden habilidades ni herramientas nuevas')
            continue
        content['highlights'].append(check.value(item, f'highlights {index}', names=True))
    roles = spec.get('experience')
    if not isinstance(roles, list) or not roles:
        check.problem('experience', 'indica al menos un puesto del perfil, en el orden deseado')
        roles = []
    content['experience'], seen = [], set()
    for index, role in enumerate(roles, 1):
        where = f'experience {index}'
        if not isinstance(role, dict) or set(role) - ROLE_KEYS or not {'title', 'company', 'dates'} <= set(role):
            check.problem(where, 'cada puesto necesita title, company, dates y bullets opcionales (description opcional)')
            continue
        title_source = role['title'] if isinstance(role['title'], str) else (role['title'] or {}).get('from') if isinstance(role['title'], dict) else None
        company_source = role['company'] if isinstance(role['company'], str) else (role['company'] or {}).get('from') if isinstance(role['company'], dict) else None
        block = profile.block(title_source, company_source) if isinstance(title_source, str) and isinstance(company_source, str) and title_source.strip() and company_source.strip() else None
        if block is None:
            check.problem(where, 'el puesto no consta en el perfil con ese título y esa empresa en la misma línea')
            continue
        key = (fold(title_source), fold(company_source))
        if key in seen:check.problem(where, 'el puesto está repetido')
        seen.add(key)
        scope = '\n'.join(block)
        entry = {'title': check.value(role['title'], where + ' title', scope, names=True),
                 'company': check.value(role['company'], where + ' company', scope, names=True),
                 'dates': check.value(role['dates'], where + ' dates', scope)}
        if role.get('description') is not None:
            entry['description'] = check.value(role['description'], where + ' description', scope)
        bullets = role.get('bullets', [])
        if not isinstance(bullets, list):
            check.problem(where, 'bullets debe ser una lista')
            bullets = []
        if len(bullets) > MAX_BULLETS:
            check.problem(where, f'tiene {len(bullets)} viñetas; el máximo es {MAX_BULLETS}')
        entry['bullets'] = [check.value(item, f'{where} bullet {n}', scope, fragment=True) for n, item in enumerate(bullets, 1)]
        content['experience'].append(entry)
    content['projects'] = []
    for index, project in enumerate(spec.get('projects', []) if isinstance(spec.get('projects', []), list) else [None], 1):
        where = f'projects {index}'
        if not isinstance(project, dict) or set(project) - PROJECT_KEYS or 'name' not in project:
            check.problem(where, 'cada proyecto necesita name y text opcional')
            continue
        content['projects'].append({'name': check.value(project['name'], where + ' name', names=True),
                                    'text': check.value(project['text'], where + ' text') if project.get('text') is not None else ''})
    for key in ('education', 'certifications'):
        items = spec.get(key, [])
        if not isinstance(items, list):
            check.problem(key, 'debe ser una lista')
            items = []
        content[key] = [check.value(item, f'{key} {n}') for n, item in enumerate(items, 1)]
    content['languages'] = check.value(spec['languages'], 'languages') if spec.get('languages') is not None else ''
    rendered = [content.get('headline', ''), content['summary'], *content['highlights'],
                *(' '.join([r['title'], r['company'], r.get('description', ''), *r['bullets']]) for r in content['experience']),
                *(p['name'] + ' ' + p['text'] for p in content['projects']), *content['education'],
                *content['certifications'], content['languages']]
    check.hidden('\n'.join(rendered), 'CV')
    if check.issues:
        raise ValueError('La adaptación no se puede usar sin inventar:\n- ' + '\n- '.join(check.issues))
    return content


def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    folder = Path('C:/Windows/Fonts')
    files = {'StubbsCV': 'arial.ttf', 'StubbsCV-Bold': 'arialbd.ttf', 'StubbsCV-Italic': 'ariali.ttf'}
    if all((folder / name).is_file() for name in files.values()):
        for font, name in files.items():
            if font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font, str(folder / name)))
        pdfmetrics.registerFontFamily('StubbsCV', normal='StubbsCV', bold='StubbsCV-Bold', italic='StubbsCV-Italic')
        return 'StubbsCV', 'StubbsCV-Bold', 'StubbsCV-Italic'
    return 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'


def render(content, person, offer_id):
    """PDF bytes of a one-page CV. person: name and optional contact fields."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold, italic = _fonts()
    ink, accent = colors.HexColor('#1F2329'), colors.HexColor('#2B4A6F')
    margin = 38
    width = A4[0] - 2 * margin - 12  # SimpleDocTemplate's frame keeps 6 pt of padding on each side
    style = lambda name, **kw: ParagraphStyle(name, fontName=kw.pop('font', regular), textColor=kw.pop('color', ink), **kw)
    S = {'name': style('name', font=bold, fontSize=19, leading=23, alignment=TA_CENTER, spaceAfter=3),
         'headline': style('headline', fontSize=10.5, leading=13, alignment=TA_CENTER, color=accent, spaceAfter=3),
         'contact': style('contact', fontSize=8.8, leading=11.5, alignment=TA_CENTER, spaceAfter=2),
         'section': style('section', font=bold, fontSize=10.6, leading=13, color=accent, spaceAfter=1),
         'body': style('body', fontSize=9, leading=11.8),
         'role': style('role', fontSize=9.2, leading=11.8),
         'date': style('date', font=bold, fontSize=8.8, leading=11.8, alignment=TA_RIGHT),
         'note': style('note', font=italic, fontSize=8.8, leading=11.4, spaceAfter=1),
         'bullet': style('bullet', fontSize=8.9, leading=11.4, leftIndent=12, firstLineIndent=-9, spaceAfter=0.6)}
    bullet_width = width - 12
    too_long = [text for role in content['experience'] for text in role['bullets']
                if stringWidth('• ' + text, regular, S['bullet'].fontSize) > bullet_width]
    if too_long:
        raise ValueError('Cada viñeta debe ocupar una línea; acorta con "text" (sin añadir datos):\n- ' + '\n- '.join(too_long))
    labels = LABELS[content['language']]
    story = [Paragraph(escape(person['name']), S['name'])]
    if content.get('headline'):story.append(Paragraph(escape(content['headline']), S['headline']))
    contact = [person.get(key) for key in ('city', 'phone', 'email', 'linkedin', 'website')]
    contact = [escape(str(value).strip()) for value in contact if isinstance(value, str) and value.strip()]
    if contact:story.append(Paragraph(' · '.join(contact), S['contact']))

    def section(key):
        story.extend([Spacer(1, 7), Paragraph(labels[key], S['section']),
                      HRFlowable(width='100%', thickness=0.5, color=ink, spaceBefore=0, spaceAfter=4)])

    section('summary')
    story.append(Paragraph(escape(content['summary']), S['body']))
    if content['highlights']:
        section('highlights')
        story.append(Paragraph(' · '.join(escape(item) for item in content['highlights']), S['body']))
    section('experience')
    for index, role in enumerate(content['experience']):
        if index:story.append(Spacer(1, 4))
        row = Table([[Paragraph(f'<font name="{bold}">{escape(role["title"])}</font> · {escape(role["company"])}', S['role']),
                      Paragraph(escape(role['dates']), S['date'])]], colWidths=[width * 0.72, width * 0.28])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')] +
                                [(name, (0, 0), (-1, -1), 0) for name in ('LEFTPADDING', 'RIGHTPADDING', 'TOPPADDING', 'BOTTOMPADDING')]))
        story.append(row)
        if role.get('description'):story.append(Paragraph(escape(role['description']), S['note']))
        story.extend(Paragraph('• ' + escape(text), S['bullet']) for text in role['bullets'])
    if content['projects']:
        section('projects')
        for project in content['projects']:
            text = f'<font name="{bold}">{escape(project["name"])}</font>' + (' – ' + escape(project['text']) if project['text'] else '')
            story.append(Paragraph(text, S['body']))
    for key in ('education', 'certifications'):
        if content[key]:
            section(key)
            story.extend(Paragraph(escape(item), S['body']) for item in content[key])
    if content['languages']:
        section('languages')
        story.append(Paragraph(escape(content['languages']), S['body']))
    buffer = io.BytesIO()
    # Invariant output: the same adaptation for the same offer gives the same file;
    # the offer ID in the metadata keeps every offer's PDF distinct.
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=34, bottomMargin=30,
                            title='CV ' + person['name'], author=person['name'], subject='Stubbs Jobs · ' + offer_id,
                            keywords=['Stubbs Jobs', offer_id], creator='Stubbs Jobs', invariant=1)
    doc.build(story)
    if doc.page != 1:
        raise ValueError(f'El CV ocupa {doc.page} páginas; elige menos viñetas, proyectos o formación para que quepa en una')
    return buffer.getvalue()


def _person(data):
    from personalization import context
    profile = data.get('profile', {})
    name = (context(data).get('name') or '').strip()
    if not name:raise ValueError('Falta tu nombre en Mi perfil; el CV no se prepara con un nombre supuesto')
    return {'name': name, 'city': profile.get('currentCity'), 'phone': profile.get('phone'), 'email': profile.get('email'),
            'linkedin': profile.get('linkedinUrl'), 'website': profile.get('websiteUrl')}


def _offer(data, op_id):
    import app_workflow as w
    rows = [row for row in data['sheets']['Oportunidades'] if row['ID'] == op_id]
    if len(rows) != 1:raise ValueError('ID de oportunidad desconocido o duplicado: ' + str(op_id))
    row = rows[0]
    if any(e.get('opportunityId') == op_id and e.get('type') == 'sent' for e in data.get('events', [])) \
            or row.get('Estado') in w.CLOSED or w.archived(data, op_id):
        raise ValueError('Esta oferta está enviada, cerrada o archivada: su CV no se cambia')
    if any(r.get('opportunityId') == op_id and r['type'] == 'send' and r['status'] == 'running' for r in w.state(data)['requests']):
        raise ValueError('Hay un envío en curso para esta oferta; su CV no se cambia')
    return row


def build(data, op_id, spec, root=None):
    """Checked content and PDF bytes for one offer, without writing anything."""
    import app_context
    root = ROOT if root is None else Path(root)
    row = _offer(data, op_id)
    content = validate(spec, app_context.experience(data), hidden_from_private(root))
    return row, content, render(content, _person(data), op_id)


def preview(data, op_id, spec, destination):
    """Write the PDF to a chosen file for inspection; the registry is not changed."""
    _, content, pdf = build(data, op_id, spec)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf)
    return {'preview': str(destination), 'cvHash': digest(pdf), 'language': content['language'], 'registered': False}


def register(data, op_id, spec):
    """Add the PDF to the CV library, assign it as «CV preparado» and declare cvAdaptation=adapted."""
    import app_workflow as w
    import stubbs_jobs
    from onboarding import require_ready
    from personalization import cv_file_name
    require_ready(data)
    row, content, pdf = build(data, op_id, spec)
    key = digest(pdf)
    relative = 'outputs/cv/' + key + '.pdf'
    others = w.cv_shared_with(data, op_id, key)
    if others:raise ValueError('Este PDF ya pertenece a otra oferta (' + ', '.join(others) + '); cada oferta necesita su CV propio')
    # A generated CV comes from the confirmed profile, so it needs no «review this CV» change request.
    stubbs_jobs.import_cv(data, cv_file_name(data, row.get('Empresa')), pdf, actor='Agente', review=False)
    operations = []
    if row.get('CV preparado') != relative:
        operations.append({'kind': 'opportunity', 'id': op_id, 'values': {'CV preparado': relative}})
    current = w.draft(data, op_id)
    values = {'cvAdaptation': 'adapted', 'cvReason': content['cvReason']}
    if any(current.get(k) != v for k, v in values.items()):
        operations.append({'kind': 'ui-draft', 'opportunityId': op_id, 'values': values,
                           'expected': {k: current.get(k) for k in values}})
    if operations:
        stubbs_jobs.apply_batch(data, {'id': 'build-cv-' + str(uuid.uuid4()), 'operations': operations})
    return {'opportunityId': op_id, 'cv': relative, 'cvHash': key, 'language': content['language'],
            'cvAdaptation': 'adapted', 'cvReason': content['cvReason'], 'registered': True, 'changed': bool(operations)}
