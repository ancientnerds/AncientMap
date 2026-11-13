import json, os, sys
from pathlib import Path
sys.path[:0] = ['scripts/remediation', '.']
from wc import cli
from phase3.run import read_jsonl
run = Path('output/remediation/wc_runner/runs') / os.environ['RUN']
drv = Path('output/remediation/final-2026-10-08/drivers/wn-and-disputes')
sweep = os.environ.get('SWEEP') == '1'   # the sweep leaves out retired rows only
rows = read_jsonl(run / 'ROWS.jsonl')
asked, listed = cli.population(rows, excluded=set(), earlier=set(), kind='wn')
pop = {e['site_id'] for e in asked}
status = {r['id']: r['scope_status'] for r in rows}
funnel = {json.loads(l)['id'] for l in open('output/remediation/final-2026-10-08/identity/IDENTITY_FUNNEL.jsonl', encoding='utf-8') if l.strip()}
hold = drv / 'wn-hold-identity.txt'
held = {l.strip() for l in hold.read_text(encoding='utf-8').splitlines() if l.strip()} if hold.exists() else set()
staged = {i for i in pop if status[i] == 'retired'}
d13 = set() if sweep else pop & funnel
other = set() if sweep else (pop & held) - d13 - staged
excl = sorted(d13 | staged | other)
out = drv / ('wn-exclude-sweep.txt' if sweep else 'wn-exclude.txt')
out.write_text(''.join(i + chr(10) for i in excl), encoding='utf-8', newline=chr(10))
n = len(pop) - len(excl)
print('empty sites the code asks:', len(pop), '| left out: D13 funnel', len(d13), '- retired', len(staged), '- identity hold', len(other),
      '| population N:', n, '| pilot size P:', min(20, n), '| stale-keys:', len(listed.get('stale-keys', [])),
      '| projected answers:', round(2.15 * n + 17))
