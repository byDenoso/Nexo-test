"""Junta os shards e aplica o criterio pre-registrado (p add-one por celula). Uso: python dde/agrega.py <pasta_com_jsonl>"""
import json, sys, pathlib
rows = []
for f in pathlib.Path(sys.argv[1]).rglob('mock_*.jsonl'):
    rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
grid = [json.loads(l) for l in open(pathlib.Path(__file__).resolve().parent / 'RESULTADO_DDE_H0' / 'saidas' / 'grade.jsonl')]
res = {}
for s in ('pantheon', 'dovekie', 'union3'):
    real = {x['configuration']: x['G'] for x in grid if x['sample'] == s and x['with_cmb'] and x['lya'] in ('2026', 'none')}
    T = max((real['C0'] - real[k]) / real['C0'] for k in ('C1', 'C2', 'C3'))
    L = [r for r in rows if r['sample'] == s and r['truth'] == 'lcdm']
    C = [r for r in rows if r['sample'] == s and r['truth'] == 'cpl']
    d = {'N_lcdm': len(L), 'N_cpl': len(C), 'T_obs': T, 'G_obs': real}
    for c in ('C0', 'C1', 'C4'):
        k = sum(r['G'][c]['G'] >= real[c] for r in L); d['p_lcdm_' + c] = [k, len(L), (k + 1) / (len(L) + 1)]
    k = sum(r['search_drop_relative'] >= T for r in C); d['p_cpl_padrao'] = [k, len(C), (k + 1) / (len(C) + 1)]
    res[s] = d
basta = all(res[s]['p_lcdm_C1'][2] > 0.05 for s in res) and all(res[s]['p_cpl_padrao'][2] < 0.05 for s in res)
sobrevive = sum(res[s]['p_lcdm_C4'][2] < 0.01 for s in res) >= 2
res['veredito'] = 'LCDM basta' if basta else ('DDE sobrevive' if sobrevive else 'inconclusivo')
print(json.dumps(res, indent=1))
open('agregado.json', 'w').write(json.dumps(res, indent=1))
