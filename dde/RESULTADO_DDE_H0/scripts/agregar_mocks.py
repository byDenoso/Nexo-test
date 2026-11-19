#!/usr/bin/env python3
"""Count actual complete simulated realizations, report k/N and add-one only."""
import pathlib,json,csv,sys
from grade_dde import OUT
rows=[]
for name in ('pantheon','dovekie','union3'):
 both={}
 for model in ('lcdm','cpl'):
  f=OUT/f'mock_summary_{name}_{model}.json'
  if not f.exists():continue
  both[model]=json.loads(f.read_text())
 if 'lcdm' not in both or 'cpl' not in both:continue
 a,b=both['lcdm'],both['cpl']
 z={'sample':name,'T_obs':a['T_observed'],'N_lcdm':a['n_complete'],'N_cpl':b['n_complete'],'seed_lcdm':a['seed'],'seed_cpl':b['seed']}
 for q in ('C0','C1','C4'):
  v=a['p_values'][q];z[f'k_lcdm_{q}']=v['k'];z[f'p_lcdm_{q}']=v['p_add_one'];z[f'kN_lcdm_{q}']=f"{v['k']}/{v['N']}"
 v=b['p_values']['pattern'];z['k_cpl_pattern']=v['k'];z['p_cpl_pattern']=v['p_add_one'];z['kN_cpl_pattern']=f"{v['k']}/{v['N']}"
 z['N_missing_lcdm']=max(0,1000-a['n_complete']);z['N_missing_cpl']=max(0,1000-b['n_complete']);rows.append(z)
with open(OUT/'pvalores_mocks.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else []);w.writeheader();w.writerows(rows)
(OUT/'quadro_decisao.json').write_text(json.dumps({'formal':'INCONCLUSIVO','reason':'Somente N=1 completo por compilacao e por modelo verdade; criterio exige 1000 mocks cada. Os p add-one minimos com N=1 sao 1/2.','mock_complete_by_sample_truth':rows,'N_requested_per_sample_truth':1000,'mock_total_complete':sum(r['N_lcdm']+r['N_cpl'] for r in rows),'mock_total_missing':sum(r['N_missing_lcdm']+r['N_missing_cpl'] for r in rows)},indent=2,ensure_ascii=False)+'\n')
print('SUMMARY',len(rows),'samples',sum(r['N_lcdm']+r['N_cpl'] for r in rows),'completed mocks',sum(r['N_missing_lcdm']+r['N_missing_cpl'] for r in rows),'missing')
