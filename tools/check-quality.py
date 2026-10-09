"""Repeatable local release checks. Job operations and real registry writes are excluded."""
import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

from runtime import configure_stdio, node_path
from stubbs_jobs_core import digest, now

ROOT = Path(__file__).resolve().parents[1]


def check(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Usa una carpeta de comprobación nueva para conservar los resultados anteriores')
    output.mkdir(parents=True)
    registry = ROOT / 'data/registry.json'
    before = digest(registry.read_bytes()) if registry.is_file() else None
    for path in (ROOT / 'tools').glob('*.py'):
        if 'conflict' not in path.name.lower():
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    node = str(node_path())
    for path in (ROOT / 'app').glob('*.js'):
        subprocess.run([node, '--check', str(path)], check=True, capture_output=True)
    tests = sorted((ROOT / 'tests').glob('test_*.cjs'))
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));sys.argv=['unittest',*sys.argv[1:]];runpy.run_module('unittest',run_name='__main__')"
    commands = [([sys.executable, '-B', '-c', bootstrap, str(ROOT/'tools'), 'discover', '-s', 'tests', '-v'], 'python.log'),
                ([node, '--test', *map(str, tests)], 'interfaz.log')]
    results = []
    for command, filename in commands:
        with (output / filename).open('wb') as handle:
            result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        log = (output / filename).read_text(encoding='utf-8', errors='replace')
        count = re.search(r'Ran (\d+) tests', log) or re.search(r'(?:# tests|ℹ tests) (\d+)', log)
        results.append({'suite': filename, 'ok': result.returncode == 0, 'tests': int(count[1]) if count else None})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        if result.returncode:
            # Keep failed checks diagnosable on CI, where the local output folder
            # disappears with the runner. The complete log remains on disk.
            print(log[-18000:], flush=True)
    after = digest(registry.read_bytes()) if registry.is_file() else None
    report = {'at': now(), 'checks': results, 'registryUnchanged': before == after,
              'ok': before == after and all(item['ok'] for item in results),
              'limits': ['Pruebas sintéticas; no acreditan una búsqueda ni un envío real.',
                         'Aceptación humana, otro ordenador y agentes reales pendientes.',
                         'Rendimiento con volumen y accesibilidad fuera del alcance de esta revisión.']}
    (output / 'resultado.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if check(args.output)['ok'] else 1)
