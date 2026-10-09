"""Read-only retention planning. Never removes archives or conflict copies."""
from datetime import datetime,timezone
import json

def plan(root):
    policy=json.loads((root/'config/retention.json').read_text(encoding='utf-8'))
    folders=[];cutoff=datetime.now(timezone.utc).timestamp()-policy['regenerableDays']*86400
    for name in ('exports','preview-cache','snapshots','workbook-backups','packages','package-staging','package-recovery','agent-runs'):
        base=root/'data'/name
        files=[p for p in base.rglob('*') if p.is_file() and not p.is_symlink()] if base.exists() else []
        candidates=[p for p in files if name in ('exports','preview-cache') and p.stat().st_mtime<cutoff and 'conflict' not in str(p).lower()]
        folders.append({'folder':name,'files':len(files),'bytes':sum(p.stat().st_size for p in files),'reviewableBytes':sum(p.stat().st_size for p in candidates)})
    return {'mode':'report-only','policy':policy,'folders':folders,'message':'No se ha borrado ningún archivo. Las copias y paquetes se conservan; revisar resultados regenerables antiguos antes de autorizar una limpieza.'}
