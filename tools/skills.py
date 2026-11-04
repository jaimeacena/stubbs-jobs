"""Competencies as their own records: one source for forms, CVs and offer fit (04/11/2026).

Only a confirmed competency can answer a form or count as met. An agent's proposal
stays visible and pending until the person confirms it; nothing here starts work.
"""
import re
import unicodedata
from functools import lru_cache

from stubbs_jobs_core import digest, now

KINDS = ('professional', 'personal', 'training')
LEVELS = ('basic', 'intermediate', 'advanced')
STATUSES = ('confirmed', 'proposed')
FIELDS = ('name', 'aliases', 'years', 'lastUsed', 'level', 'kind', 'usedAt')


def fold(text):
    """Lower case without accents or stray spaces, keeping the symbols of names like C# or T-SQL."""
    plain = unicodedata.normalize('NFD', str(text or ''))
    plain = ''.join(char for char in plain if not unicodedata.combining(char))
    return ' '.join(plain.casefold().split())


def listing(data):
    return data.get('app', {}).get('skills', [])


def confirmed(data):
    return [skill for skill in listing(data) if skill.get('status') == 'confirmed']


def names(skill):
    return [skill['name'], *(skill.get('aliases') or [])]


@lru_cache(maxsize=2048)
def _name_pattern(name):
    return re.compile(r'(?<![\w/+#-])' + re.escape(fold(name)) + r'(?![\w+#]|/\w|-\w)')


def mentions(text, name):
    """Whole-name match: «R» is not found in «Power», and «SQL» is not found in «PL/SQL»."""
    return bool(_name_pattern(name).search(fold(text)))


def find(data, name, only_confirmed=False):
    wanted = fold(name)
    pool = confirmed(data) if only_confirmed else listing(data)
    return next((skill for skill in pool if wanted in map(fold, names(skill))), None)


def view(data):
    """Pending first, then the longest experience, so a person sees what needs attention."""
    from form_rules import whole_years
    rows = []
    for skill in listing(data):
        years = skill.get('years')
        rows.append({**skill, 'formYears': whole_years(years) if type(years) in (int, float) else None,
                     'pending': skill.get('status') != 'confirmed' or years is None})
    rows.sort(key=lambda row: (not row['pending'], -(row['years'] or 0), fold(row['name'])))
    return rows


def _clean(values):
    if not isinstance(values, dict) or set(values)-set(FIELDS):
        raise ValueError('Esa competencia tiene campos no admitidos')
    name = values.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Escribe el nombre de la competencia')
    aliases = values.get('aliases') or []
    if not isinstance(aliases, list) or len(aliases) > 12 or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 80 for a in aliases):
        raise ValueError('Revisa los otros nombres de la competencia')
    years = values.get('years')
    if years is not None and (type(years) not in (int, float) or not 0 <= years <= 60):
        raise ValueError('Indica los años con un número entre 0 y 60, o déjalos en blanco')
    level, kind = values.get('level'), values.get('kind') or 'professional'
    if level is not None and level not in LEVELS:
        raise ValueError('Indica el nivel: básico, intermedio o avanzado')
    if kind not in KINDS:
        raise ValueError('Indica si la usas en el trabajo, en proyectos propios o en formación')
    result = {'name': name.strip(), 'aliases': [a.strip() for a in aliases if fold(a) != fold(name)], 'years': years, 'level': level, 'kind': kind}
    for key, limit in (('lastUsed', 20), ('usedAt', 500)):
        text = values.get(key)
        if text is not None and (not isinstance(text, str) or len(text) > limit):
            raise ValueError('Revisa el texto de la competencia')
        result[key] = text.strip() if text and text.strip() else None
    return result


def handle(data, op):
    """Save or remove one competency; the person's interface confirms, an agent proposes."""
    kind = op['kind']
    if kind not in ('ui-skill-save', 'ui-skill-remove'):
        return False
    import app_workflow as workflow
    app = workflow.state(data)
    skills = app.setdefault('skills', [])
    actor, proof = op.get('actor', 'Agente'), op.get('proof')
    by_person = workflow.chosen_by_person(actor)
    if not by_person and (not isinstance(proof, str) or not 10 <= len(proof.strip()) <= 2000):
        raise ValueError('Indica de dónde sale este dato: el CV, la experiencia o las palabras de la persona')
    identifier = op.get('id')
    current = next((skill for skill in skills if skill['id'] == identifier), None)
    if identifier and current is None:
        raise ValueError('Esa competencia ya no existe; actualiza el estado')
    if 'expected' in op:
        workflow.expect(current, op['expected'])
    if kind == 'ui-skill-remove':
        if current is None:
            raise ValueError('Indica la competencia que quieres quitar')
        skills.remove(current)
        workflow.record(data, 'Competencia retirada: '+current['name'], actor=actor, detail=proof or 'Retirada desde Mi perfil.')
        return True
    values = _clean(op.get('values'))
    other_names = {fold(name) for skill in skills if skill is not current for name in names(skill)}
    if {fold(name) for name in names(values)} & other_names:
        raise ValueError('Ya tienes una competencia con ese nombre: edítala en lugar de duplicarla')
    status = op.get('status', 'confirmed' if by_person else 'proposed')
    if status not in STATUSES:
        raise ValueError('Indica si la competencia está confirmada o propuesta')
    if current and current.get('status') == 'confirmed' and status == 'proposed':
        raise ValueError('Esta competencia ya está confirmada; una propuesta no la sustituye')
    record = {'id': current['id'] if current else 'skill-'+digest(fold(values['name']))[:12], **values, 'status': status,
              'updatedAt': now(), 'source': 'person' if by_person else 'agent'}
    if proof:
        record['proof'] = proof.strip()
    if current:
        skills[skills.index(current)] = record
    else:
        skills.append(record)
    workflow.record(data, ('Competencia guardada: ' if status == 'confirmed' else 'Competencia propuesta: ')+record['name'], actor=actor, detail=proof or 'Guardada desde Mi perfil.')
    return True
