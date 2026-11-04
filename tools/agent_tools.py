"""Tools recommended to the person's AI agent, with their last real check (04/11/2026).

A record is a dated check, never a lasting connection or a permission: connecting
the mail does not allow reading it, and nothing here starts work.
"""
from datetime import datetime, timedelta, timezone

from state_support import instant
from stubbs_jobs_core import now

GUIDE = 'docs/agent-tools.md'
STALE_DAYS = 30
STATUSES = ('connected', 'unavailable', 'declined')
TOOLS = {
    'browser': {'label': 'Extensión del navegador',
                'why': 'Permite buscar y solicitar con tus sesiones abiertas y adjuntar un CV adaptado a cada oferta.',
                'withoutIt': 'Tendrías que abrir sesión en el navegador del agente y muchos formularios no admitirían un CV propio.'},
    'mail': {'label': 'Conector de correo',
             'why': 'Permite completar la verificación que pide un portal y localizar el recibo de una solicitud dudosa.',
             'withoutIt': 'Tendrías que confirmar tú esos correos.'},
}
STATUS_TEXT = {'connected': 'Conectado', 'unavailable': 'No disponible con tu agente', 'declined': 'Prefieres no usarlo', None: 'Sin conectar'}


def _stale(record):
    moment = instant(record.get('checkedAt'))
    return moment is None or datetime.now(timezone.utc)-moment > timedelta(days=STALE_DAYS)


def view(data):
    """Read-only state of each tool; a connection is checked again after a while."""
    saved = data.get('app', {}).get('agentTools', {})
    tools, pending = [], []
    for key, tool in TOOLS.items():
        record = saved.get(key) or {}
        status = record.get('status')
        stale = status == 'connected' and _stale(record)
        if status is None or stale:
            pending.append(key)
        tools.append({'key': key, **tool, 'status': status, 'statusText': 'Por comprobar de nuevo' if stale else STATUS_TEXT[status],
                      'agent': record.get('agent'), 'checkedAt': record.get('checkedAt'), 'recheck': stale})
    return {'tools': tools, 'pending': pending, 'guide': GUIDE,
            'nextStep': ('Guía a la persona paso a paso con ' + GUIDE + ', de una en una, y registra cada comprobación con ui-tool-readiness.') if pending else None,
            'meaning': 'Registro fechado de la última comprobación; no prueba la conexión actual ni concede permisos.'}


def handle(data, op):
    """Save a real check by the agent or the person's decision."""
    if op['kind'] != 'ui-tool-readiness':
        return False
    import app_workflow as workflow
    tool, status, proof, agent = op.get('tool'), op.get('status'), op.get('proof'), op.get('agent')
    if tool not in TOOLS:
        raise ValueError('Indica la herramienta: browser o mail')
    if status not in STATUSES:
        raise ValueError('Indica el resultado: connected, unavailable o declined')
    if not isinstance(proof, str) or not 10 <= len(proof.strip()) <= 2000:
        raise ValueError('Indica qué comprobaste o las palabras de la persona')
    if not isinstance(agent, str) or not 1 <= len(agent.strip()) <= 100:
        raise ValueError('Indica el agente con el que se comprobó')
    workflow.state(data).setdefault('agentTools', {})[tool] = {'status': status, 'agent': agent.strip(), 'checkedAt': now(), 'proof': proof.strip()}
    workflow.record(data, TOOLS[tool]['label']+': '+STATUS_TEXT[status].lower(), actor=op.get('actor', 'Agente'), detail=proof.strip())
    return True
