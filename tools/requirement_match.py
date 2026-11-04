"""Advice on how an offer's written requirements compare with confirmed competencies (04/11/2026).

It reads words, not meaning: its result orders attention and never archives an offer,
blocks a send or replaces the person's choice. Minimums keep their own rules.
"""
import collections
import re

import skills
from form_rules import whole_years
from view_cache import memo

# Common tools found in adverts, so one the person lacks can be named. A person's own
# competencies work for any occupation, with or without this list.
VOCABULARY = {
    'Power BI': ['power bi', 'powerbi'], 'DAX': ['dax'], 'Power Query': ['power query'], 'Microsoft Fabric': ['microsoft fabric', 'ms fabric'],
    'SQL': ['sql', 't-sql', 'tsql', 'sql server'], 'PL/SQL': ['pl/sql', 'plsql'], 'Python': ['python'], 'PySpark': ['pyspark'], 'Spark': ['spark', 'apache spark'], 'R': ['r studio', 'rstudio'],
    'Excel': ['excel'], 'Tableau': ['tableau'], 'Qlik': ['qlik', 'qlikview', 'qliksense'], 'Looker': ['looker'], 'QuickSight': ['quicksight'], 'SSIS': ['ssis'], 'SSAS': ['ssas'], 'SSRS': ['ssrs'],
    'Snowflake': ['snowflake'], 'Databricks': ['databricks'], 'dbt': ['dbt'], 'Airflow': ['airflow'], 'BigQuery': ['bigquery'], 'Redshift': ['redshift'], 'Synapse': ['synapse'], 'Kafka': ['kafka'],
    'AWS': ['aws', 'amazon web services'], 'Azure': ['azure'], 'GCP': ['gcp', 'google cloud'], 'SAP': ['sap'], 'Salesforce': ['salesforce'], 'Java': ['java'], 'Scala': ['scala'],
    'JavaScript': ['javascript'], 'TypeScript': ['typescript'], 'Git': ['git', 'github', 'gitlab'], 'Docker': ['docker'], 'Kubernetes': ['kubernetes'], 'Power Automate': ['power automate'], 'Power Apps': ['power apps', 'powerapps'],
}
SEPARATORS = re.compile(r'\s*\|\s*|\n+|(?<=[.;:])\s+|\s+[•·]\s+')
NICE = re.compile(r'valorable|valora|deseable|se valorar|nice to have|nice-to-have|\bplus\b|bonus|preferred|preferible|would be|ideally|es un extra|a favor')
MUST = re.compile(r'imprescindible|obligatori|requisito|requirement|required|must|necesari|indispensable|debes|you have|you bring|buscamos|what we need|minimo|at least')
EVIDENCE = re.compile(r'experiencia|experience|conocimiento|knowledge|dominio|proficien|solid|solida|fluent|manejo|skills?\b')
NOT_NEEDED = re.compile(r'no (es )?(necesari|imprescindible|requerid)|not required|no se requiere')
YEARS = re.compile(r'(\d{1,2})\s*(?:\+|o mas|or more|años|anos|years|yrs)')
RANK = {'must': 2, 'nice': 1, 'mentioned': 0}


def _sentences(text):
    """Headings set the level of what follows, until the next heading changes it."""
    section = None
    for part in SEPARATORS.split(str(text or '')):
        words = skills.fold(part)
        if not words:
            continue
        heading = len(words) < 60
        if NICE.search(words):
            if heading:
                section = 'nice'
            yield words, 'nice'
            continue
        if MUST.search(words):
            if heading:
                section = 'must'
            yield words, 'must'
            continue
        yield words, section or ('must' if EVIDENCE.search(words) else 'mentioned')


def _terms(data):
    terms = [(name, skill['name'], skill) for skill in skills.listing(data) for name in skills.names(skill)]
    known = {skills.fold(name) for name, _, _ in terms}
    for canonical, aliases in VOCABULARY.items():
        for alias in aliases:
            if skills.fold(alias) not in known:
                terms.append((alias, canonical, None))
    return sorted(terms, key=lambda term: -len(term[0]))


def analyse(data, text):
    found = {}
    # Most tools never appear: discard them once over the whole advert, not per sentence.
    whole = skills.fold(text)
    terms = [term for term in _terms(data) if skills.fold(term[0]) in whole]
    for sentence, level in _sentences(text) if terms else ():
        if NOT_NEEDED.search(sentence):
            continue
        asked = max(map(int, YEARS.findall(sentence)), default=None)
        for name, canonical, skill in terms:
            if not skills._name_pattern(name).search(sentence):
                continue
            item = found.setdefault(canonical, {'name': canonical, 'skill': skill, 'level': level, 'years': None})
            if RANK[level] > RANK[item['level']]:
                item['level'] = level
            if asked is not None and level != 'nice':
                item['years'] = max(item['years'] or 0, asked)
    groups = {'met': [], 'gaps': [], 'missing': [], 'unclear': [], 'niceToHave': []}
    for item in found.values():
        skill = item['skill'] or skills.find(data, item['name'])
        have = skill.get('years') if skill else None
        known = bool(skill and skill.get('status') == 'confirmed')
        row = {'name': item['name'], 'level': item['level']}
        if item['years'] is not None:
            row['askedYears'] = item['years']
        if known and have is not None:
            row['yourYears'] = whole_years(have)
        if known and have == 0:
            groups['niceToHave' if item['level'] == 'nice' else 'missing' if item['level'] == 'must' else 'unclear'].append(row if item['level'] != 'mentioned' else {**row, 'reason': 'El anuncio la menciona y no tienes experiencia'})
        elif known and (item['years'] is None or (have is not None and whole_years(have) >= item['years'])):
            groups['met'].append(row)
        elif known and have is not None:
            groups['gaps'].append(row)
        elif skill:
            groups['unclear'].append({**row, 'reason': 'Por confirmar en tus competencias'})
        elif item['level'] == 'must':
            groups['missing'].append(row)
        elif item['level'] == 'nice':
            groups['niceToHave'].append(row)
        else:
            groups['unclear'].append({**row, 'reason': 'El anuncio la menciona sin decir si la exige'})
    for rows in groups.values():
        rows.sort(key=lambda row: row['name'].casefold())
    return groups


def verdict(groups):
    required = [row for row in groups['met'] if row['level'] == 'must']
    blocking = len(groups['missing'])+len(groups['gaps'])
    if not any(groups.values()):
        return 'unknown'
    if not blocking:
        return 'strong' if required or groups['met'] else 'unknown'
    return 'partial' if required and blocking <= len(required) else 'weak'


def for_offer(data, row):
    def compute():
        # The agent's quotes of the advert count; its own opinion in the assessment does not.
        assessment = data.get('app', {}).get('offerAssessments', {}).get(row['ID']) or {}
        quotes = [item.get('text') for item in assessment.get('references') or [] if isinstance(item, dict) and item.get('text')]
        text = ' | '.join([str(row[name]) for name in ('Requisitos de la oferta', 'Tecnologías') if row.get(name)]+quotes)
        basis = 'Comparación por palabras: orienta, no decide ni descarta.'
        # Without confirmed competencies, every requirement would look like a false lack.
        if not skills.confirmed(data):
            return {'met': [], 'gaps': [], 'missing': [], 'unclear': [], 'niceToHave': [], 'verdict': 'unknown', 'needsSkills': True, 'basis': basis}
        groups = analyse(data, text)
        return {**groups, 'verdict': verdict(groups), 'basis': basis}
    return memo(('requirement-match', id(data), row['ID']), compute)


def gaps_summary(data, limit=10):
    """Requirements most often missing from open offers: where learning would open most doors."""
    import app_workflow as workflow
    counter = collections.Counter()
    for row in data['sheets']['Oportunidades']:
        if row.get('Estado') in workflow.CLOSED or workflow.archived(data, row['ID']):
            continue
        result = for_offer(data, row)
        counter.update(item['name'] for item in (*result['missing'], *result['gaps']))
    return counter.most_common(limit)


PRIORITY_BY_VERDICT = {'strong': 'A', 'partial': 'B', 'unknown': 'B', 'weak': 'C'}


def suggested_priority(fit):
    """The priority an offer gets from its requirements: same facts, same answer, for any agent."""
    return PRIORITY_BY_VERDICT.get((fit or {}).get('verdict'), 'B')
