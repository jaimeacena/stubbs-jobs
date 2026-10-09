"""Recorded first-run progress, not a persistent connection to an agent."""
import copy
import os
import uuid
import profile_interview as interview
from stubbs_jobs_core import ROOT, digest, now


def initial():
    return {'token':uuid.uuid4().hex,'revision':0,'status':'waiting','draft':{},'fieldDecisions':{}}


def workspace_id(root=None):
    return digest(str((root or ROOT).resolve()))[:24]


def view(data, root=None):
    app=data.get('app',{});saved=app.get('onboarding',{})
    # Older incomplete installations get a stable challenge without a read writing data.
    token=saved.get('token') or digest(['setup',data.get('createdAt'),workspace_id(root)])
    ready=app.get('setupComplete',True)
    moved=not ready and saved.get('workspaceId') not in (None,workspace_id(root))
    coverage=copy.deepcopy(saved.get('completedCoverage')) if ready else interview.coverage(data,saved.get('draft',{}),saved.get('fieldDecisions',{}))
    status=saved.get('status','waiting')
    if not ready and status=='awaiting_confirmation' and not coverage['complete']:status='preparing'
    return {'status':'ready' if ready else 'blocked' if moved else status,
            'token':token,'revision':saved.get('revision',0),'workspaceId':workspace_id(root),
            'agent':saved.get('agent',''),'executionId':saved.get('executionId'),
            'checkedAt':None if moved else saved.get('checkedAt'),'updatedAt':saved.get('updatedAt'),
            'summary':'La carpeta ha cambiado. Pulsa «Retomar en otro chat» para comprobar el acceso de nuevo.' if moved else saved.get('summary',''),
            'draft':copy.deepcopy(saved.get('draft',{})),
            'fieldDecisions':copy.deepcopy(saved.get('fieldDecisions',{})),
            'coverage':coverage,
            'needsWelcome':bool(ready and saved.get('completedAt') and not saved.get('acknowledgedAt'))}


def require_ready(data):
    if data.get('app',{}).get('setupComplete',True) is False:
        raise ValueError('Completa y confirma primero el perfil inicial con tu agente. La preparación no inicia búsquedas ni solicitudes.')


def check(data,op,agent=False):
    import app_workflow as w
    current=view(data)
    if op.get('workspaceId')!=current['workspaceId'] or op.get('token')!=current['token']:
        raise w.Conflict('Esta preparación pertenece a otra carpeta o intento. Relee app-status antes de continuar.')
    if type(op.get('expected')) is not int:raise ValueError('Indica la revisión actual de la preparación')
    w.expect(current['revision'],op['expected'])
    if agent:
        owner=os.environ.get('STUBBS_JOBS_EXECUTION_ID')
        if not owner:raise ValueError('Usa --execution-id con un identificador propio para preparar el perfil')
        if current['executionId'] and current['executionId']!=owner:
            raise w.Conflict('Otro chat está preparando el perfil. Para cambiar de chat, pulsa «Retomar en otro chat» en la app.')
    return current


def handle(data,op):
    import app_workflow as w
    from personalization import validate_initial
    kind=op['kind']
    if kind not in ('ui-setup-progress','ui-setup-retry','ui-setup-finish'):return False
    app=w.state(data);current=check(data,op,agent=kind=='ui-setup-progress')
    if kind=='ui-setup-finish':
        require_ready(data)
        saved=app.get('onboarding')
        if saved and not saved.get('acknowledgedAt'):saved['acknowledgedAt']=now();saved['revision']+=1
        return True
    if app.get('setupComplete',True):raise ValueError('El perfil ya está preparado; puedes editarlo en Mi perfil')
    if kind=='ui-setup-retry':
        saved=initial();saved['revision']=current['revision']+1
        saved['draft']=current['draft'];saved['updatedAt']=now()
        saved['fieldDecisions']=current['fieldDecisions']
        app['onboarding']=saved
        w.record(data,'Preparación retomada en otro chat',actor=op.get('actor','Usuario'))
        return True
    status=op.get('status');previous=current['status']
    transitions={'waiting':{'access_checked'},'access_checked':{'access_checked','preparing','awaiting_confirmation','blocked'},
                 'preparing':{'access_checked','preparing','awaiting_confirmation','blocked'},
                 'awaiting_confirmation':{'access_checked','preparing','awaiting_confirmation','blocked'},
                 'blocked':{'access_checked'}}
    if status not in transitions.get(previous,set()):raise ValueError('Comprueba el acceso antes de continuar la preparación')
    agent=op.get('agent');summary=op.get('summary');proof=op.get('proof')
    if not isinstance(agent,str) or not agent.strip() or len(agent)>80:raise ValueError('Indica el agente que comprobó la carpeta')
    if not isinstance(summary,str) or not summary.strip() or len(summary)>300:raise ValueError('Explica el paso o problema en una frase')
    if not isinstance(proof,str) or not proof.strip() or len(proof)>2000:raise ValueError('Conserva la comprobación realizada')
    values=op.get('values',current['draft'])
    validate_initial(values,data=data)
    field_decisions=interview.decisions(data,values,current['fieldDecisions'],op.get('fieldDecisions',{}))
    if status=='awaiting_confirmation':interview.require_complete(data,values,field_decisions)
    saved=copy.deepcopy(app.get('onboarding',{}))
    saved.update(token=current['token'],revision=current['revision']+1,status=status,agent=agent.strip(),
                 executionId=os.environ.get('STUBBS_JOBS_EXECUTION_ID'),workspaceId=current['workspaceId'],updatedAt=now(),
                 summary=summary.strip(),proof=proof.strip(),draft=copy.deepcopy(values),fieldDecisions=field_decisions)
    if status=='access_checked':saved['checkedAt']=now()
    app['onboarding']=saved
    w.record(data,'Preparación inicial actualizada',actor='Agente',detail=summary.strip())
    return True


def confirm(data,op):
    import app_workflow as w
    current=check(data,{**op,'expected':op.get('expectedSetupRevision')},agent=True)
    if current['status']!='awaiting_confirmation' or not current['checkedAt']:
        raise ValueError('Comprueba el acceso y muestra el resumen del perfil antes de guardarlo')
    if current['draft']!=op.get('values'):raise w.Conflict('El resumen cambió. Muestra la nueva versión y pide su confirmación antes de guardar.')
    interview.require_complete(data,current['draft'],current['fieldDecisions'])
    proof=op.get('proof')
    if not isinstance(proof,str) or not proof.strip() or len(proof)>2000:
        raise ValueError('Conserva la confirmación expresa del resumen por la persona')


def completed(data,op):
    saved=data['app']['onboarding']
    saved['completedCoverage']=interview.require_complete(data,saved.get('draft',{}),saved.get('fieldDecisions',{}))
    saved.update(status='ready',completedAt=now(),updatedAt=now(),summary='Perfil confirmado y guardado.',confirmation=op['proof'].strip())
    saved['revision']+=1
    saved.pop('draft',None)
