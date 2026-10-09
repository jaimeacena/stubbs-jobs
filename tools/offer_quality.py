"""Evidence-backed offer explanations. Assessments never grant sending permission."""
from urllib.parse import urlsplit
import copy
import re
from datetime import datetime,timedelta,timezone
from state_support import instant

from stubbs_jobs_core import now, digest


def fingerprint(data, row):
    import app_context
    return digest([app_context.fit_stamp(data, row), app_context.experience(data)])


def best_argument(data, value, references):
    """Bind one complete experience statement to an already checked offer source."""
    import app_context
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'experienceQuote', 'referenceIndex'}:
        raise ValueError('El argumento necesita un ejemplo de Mi experiencia y su fuente de la oferta.')
    quote, index = value['experienceQuote'], value['referenceIndex']
    if not isinstance(quote, str) or not 20 <= len(quote.strip()) <= 320:
        raise ValueError('Elige un ejemplo completo y breve de Mi experiencia, de 20 a 320 caracteres.')
    # Keep the whole statement, including qualifiers; a matching keyword is not evidence.
    normalize = lambda text: re.sub(r'\s+', ' ', text).strip()
    statements = {normalize(re.sub(r'^\s*[-*+]\s+', '', line))
                  for line in app_context.experience(data).splitlines()
                  if line.strip() and not line.lstrip().startswith('#')}
    quote = normalize(quote)
    if quote not in statements:
        raise ValueError('Copia una frase o viñeta completa de Mi experiencia, sin quitar sus límites ni añadir hechos.')
    if type(index) is not int or not 0 <= index < len(references):
        raise ValueError('Vincula el ejemplo a una de las fuentes comprobadas de esta oferta.')
    reference = references[index]
    requirement = normalize(reference['text'])
    if len(requirement) > 180:
        raise ValueError('Resume el requisito comprobado de esa fuente en un máximo de 180 caracteres.')
    return {'experienceQuote': quote, 'requirement': requirement, 'sourceUrl': reference['url']}


def current_argument(data, row):
    record = view(data, row)
    return copy.deepcopy(record.get('bestArgument')) if record and record['isCurrent'] else None


def assess(data, operation, workflow):
    key = operation.get('opportunityId')
    row = workflow.row_for(data, key)
    current = fingerprint(data, row)
    if operation.get('fingerprint') != current:
        raise workflow.Conflict('Los criterios o la oferta cambiaron. Comprueba su encaje antes de guardar la valoración.')
    reason = operation.get('reason')
    proof = operation.get('proof')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 400:
        raise ValueError('Explica brevemente por qué merece atención esta oferta, o por qué se descarta.')
    if not isinstance(proof, str) or not proof.strip() or len(proof) > 15000:
        raise ValueError('La valoración necesita una prueba concreta de lo comprobado.')
    observed=instant(operation.get('observedAt'))
    if not observed or observed>datetime.now(timezone.utc)+timedelta(minutes=5):
        raise ValueError('Indica observedAt: fecha real con zona horaria de consulta de las fuentes, sin fechas futuras')
    references = operation.get('references')
    if not isinstance(references, list) or not 1 <= len(references) <= 5:
        raise ValueError('Añade de una a cinco fuentes comprobadas para esta valoración.')
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != {'url', 'text'}:
            raise ValueError('Cada fuente necesita su enlace y el hecho que demuestra.')
        url, text = reference['url'], reference['text']
        if (not isinstance(url, str) or len(url) > 2000 or urlsplit(url).scheme not in ('http', 'https') or
                not urlsplit(url).hostname or not isinstance(text, str) or not text.strip() or len(text) > 500):
            raise ValueError('Revisa el enlace y el hecho concreto de cada fuente.')
    unknowns = operation.get('unknowns', [])
    if (not isinstance(unknowns, list) or len(unknowns) > 8 or
            any(not isinstance(text, str) or not text.strip() or len(text) > 300 for text in unknowns)):
        raise ValueError('Indica las dudas concretas que quedan por comprobar.')
    record = {'fingerprint': current, 'reason': reason.strip(), 'references': copy.deepcopy(references),
              'unknowns': list(unknowns), 'proof': proof, 'at': now(),'observedAt':operation['observedAt']}
    argument = best_argument(data, operation.get('bestArgument'), references)
    if argument:
        record['bestArgument'] = argument
    workflow.state(data).setdefault('offerAssessments', {})[key] = record
    workflow.record(data, 'Valoración de la oferta guardada', key, operation.get('actor', 'Agente'), reason.strip())


def view(data, row):
    record = data.get('app', {}).get('offerAssessments', {}).get(row['ID'])
    if not record:
        return None
    current = record.get('fingerprint') == fingerprint(data, row)
    observed=instant(record.get('observedAt'))
    fresh=bool(observed and datetime.now(timezone.utc)-observed<=timedelta(days=7))
    return {**record, 'isCurrent': current, 'fresh': fresh}
