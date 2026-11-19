#!/usr/bin/env python3
"""Export completed JSONL to inspectable CSV / full-model best-fit table."""
import csv,json,sys
from grade_dde import OUT
rows=[json.loads(x) for x in open(OUT/'grade.jsonl') if x.strip()]
rows.sort(key=lambda x:(x['sample'],x['with_cmb'],x['configuration'],x['lya']))
with open(OUT/'grade_completa.csv','w',newline='') as f:
 cols=['compilacao','cmb','configuracao','lyalpha','G','custo_nao_fantasma','modelo','chi2','chi2_SN','chi2_BAO','chi2_CMB','Omega_m','w0','wa','H0_rd_km_s','H0_km_s_Mpc','rdrag_Mpc','avaliacoes_funcao','n_inicios']
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for r in rows:
  for m in ('lcdm','cpl','qinf'):
   o=r['models'][m];a=o['components']
   w.writerow({'compilacao':r['sample'],'cmb':int(r['with_cmb']),'configuracao':r['configuration'],'lyalpha':r['lya'],
     'G':f"{r['G']:.8f}",'custo_nao_fantasma':f"{r['cost_nonphantom']:.8f}",
     'modelo':m,'chi2':f"{o['chi2']:.8f}",'chi2_SN':a['chi2_sn'],'chi2_BAO':a['chi2_bao'],'chi2_CMB':a['chi2_cmb'],
     'Omega_m':a['om'],'w0':a['w0'],'wa':a['wa'],'H0_rd_km_s':a['H0rd'],'H0_km_s_Mpc':a['H0'],'rdrag_Mpc':a['rd'],
     'avaliacoes_funcao':o['nfev'],'n_inicios':8})
with open(OUT/'grade_resumo.csv','w',newline='') as f:
 cols=['compilacao','cmb','configuracao','lyalpha','G','custo_nao_fantasma','Omega_m_CPL','w0_CPL','wa_CPL','H0_rd_CPL','H0_CPL']
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for r in rows:
  a=r['models']['cpl']['components'];w.writerow({'compilacao':r['sample'],'cmb':int(r['with_cmb']),'configuracao':r['configuration'],'lyalpha':r['lya'],
   'G':f"{r['G']:.5f}",'custo_nao_fantasma':f"{r['cost_nonphantom']:.5f}",
   'Omega_m_CPL':a['om'],'w0_CPL':a['w0'],'wa_CPL':a['wa'],'H0_rd_CPL':a['H0rd'],'H0_CPL':a['H0']})
print('EXPORTED',len(rows),'configurations',len(rows)*3,'bestfits')
