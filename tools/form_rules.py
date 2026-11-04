"""Rules for answering application forms from confirmed data (04/11/2026).

Read-only: nothing here writes the registry, chooses an offer or sends anything.
"""
import re
import urllib.request
import xml.etree.ElementTree as ElementTree
from decimal import ROUND_HALF_UP, Decimal

ECB_DAILY = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
PERIODS = {'year', 'month'}
GENERAL_RULES = (
    'Antes de responder una pregunta nueva, usa answer-lookup: use=answer se responde, use=suggest se comprueba y use=ask no se inventa.',
    'Lo ya respondido se reutiliza sin volver a preguntar. Responde en el idioma del formulario y con sus opciones.',
    'Solo pregunta a la persona lo que su perfil no permite responder y guárdalo en español con ui-answer-save, sin nombres de empresas.',
    'Años en un campo que solo admite enteros: usar el entero más cercano (3,7 → 4), nunca truncar.',
    'Una competencia o respuesta confirmada prevalece sobre el cálculo con fechas.',
    'Sin competencia guardada: deducir solo lo que figure en la experiencia y proponerla con ui-skill-save; si no consta, no inventar.',
    'Otra moneda o periodo: usar salary-answer y anotar tipo, fecha y número de pagas en proof.',
    'minimumFixed es un límite interno: nunca se responde en un formulario.',
)


def whole_years(value):
    """Nearest whole number of years, with halves rounding up (3.7 -> 4, 2.5 -> 3)."""
    if type(value) not in (int, float) or value < 0:
        raise ValueError('Indica los años con un número positivo')
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def view(data):
    """Saved answers an agent needs before filling in a form, with what is still unanswered."""
    import answer_bank
    import skills
    rows = sorted(skills.view(data), key=lambda row: row['name'].casefold())
    bank = answer_bank.listing(data)
    return {'skills': [{key: row.get(key) for key in ('name', 'aliases', 'years', 'formYears', 'lastUsed', 'level', 'kind', 'status')} for row in rows],
            'pendingSkills': [row['name'] for row in rows if row['pending']],
            'answers': {'saved': len(bank), 'conflicts': sum(1 for entry in bank if entry.get('conflict'))},
            'lookupCommand': 'answer-lookup --case ID_OFERTA --question "texto de la pregunta"',
            'salary': _salary(data),
            'conversionCommand': 'salary-answer --case ID_OFERTA --currency USD --period month',
            'rules': list(GENERAL_RULES)}


def _salary(data):
    """The form salary of each search profile; an offer uses the one of its profile."""
    import search_profiles
    shown = lambda value: {'amount': value['salaryExpectationFixed'], 'currency': value['salaryCurrency'], 'period': 'year'}
    result = shown(search_profiles.form_salary(data))
    if 'searchProfiles' in data.get('app', {}):
        result['byProfile'] = {p['id']: shown(search_profiles.form_salary(data, p['id'])) for p in search_profiles.visible_profiles(data)}
    return result


def _download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'StubbsJobs'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def ecb_rates(download=_download):
    """Latest euro reference rates published by the European Central Bank."""
    try:
        root = ElementTree.fromstring(download(ECB_DAILY))
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError('No se pudo consultar el tipo de cambio del BCE; no respondas con una cifra supuesta') from exc
    day = next((node for node in root.iter() if node.tag.endswith('Cube') and node.get('time')), None)
    if day is None:
        raise ValueError('El BCE no devolvió un tipo de cambio reconocible; no respondas con una cifra supuesta')
    rates = {'EUR': Decimal('1')}
    for node in day:
        if node.get('currency') and node.get('rate'):
            rates[node.get('currency').upper()] = Decimal(node.get('rate'))
    return day.get('time'), rates


def salary_answer(data, currency, period='year', payments=12, download=_download, case=None, search_profile_id=None):
    """Convert the saved form salary into the currency and period a form asks for."""
    import search_profiles
    salary = search_profiles.offer_form_salary(data, case) if case else search_profiles.form_salary(data, search_profile_id)
    amount, source = salary['salaryExpectationFixed'], salary['salaryCurrency']
    if type(amount) not in (int, float) or amount <= 0 or not isinstance(source, str) or not source.strip():
        raise ValueError('Guarda primero en Mi perfil › Lo que busco el salario para formularios de ese perfil y su moneda')
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Za-z]{3}', currency):
        raise ValueError('Indica la moneda con su código de tres letras, por ejemplo USD')
    if period not in PERIODS:
        raise ValueError('Indica el periodo: year o month')
    if type(payments) is not int or not 1 <= payments <= 16:
        raise ValueError('Indica un número de pagas entre 1 y 16')
    source, currency = source.strip().upper(), currency.upper()
    rate, day = Decimal('1'), None
    if currency != source:
        day, rates = ecb_rates(download)
        if source not in rates or currency not in rates:
            raise ValueError('El BCE no publica un tipo de cambio para ' + (source if source not in rates else currency))
        rate = rates[currency] / rates[source]
    annual = Decimal(str(amount)) * rate
    value = annual if period == 'year' else annual / payments
    rounded = int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    basis = f'{amount} {source} brutos al año'
    if currency != source:
        basis += f', tipo BCE {float(rate):.4f} del {day}'
    if period == 'month':
        basis += f', {payments} pagas'
    return {'amount': rounded, 'currency': currency, 'period': period, 'payments': payments if period == 'month' else None,
            'rate': float(rate), 'rateDate': day, 'source': ECB_DAILY if day else None,
            'authorized': data.get('profile', {}).get('autoApplyDerivedAnswers') is True,
            'proof': f'{rounded} {currency} ' + ('al año' if period == 'year' else 'al mes') + f' ({basis}).'}
