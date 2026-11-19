#!/usr/bin/env python3
"""Run hard data SHA check and numerical sanity checks on grid."""
import json,hashlib,pathlib,sys
import numpy as np
from grade_dde import R,D,OUT,SN,integral
out={}
checks=[]
for line in (R/'SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split(maxsplit=1);f=R/rel
 hh=hashlib.sha256(f.read_bytes()).hexdigest()
 checks.append((rel,hh==h,hh))
out['sha256_files_checked']=len(checks);out['sha256_all_match']=all(x[1] for x in checks)
out['sha256_results']=[dict(path=p,match=good,sha256=hh) for p,good,hh in checks]
errors=[]
for name in ('pantheon','dovekie','union3'):
 sn=SN(name)
 for o,w0,wa in [(.3,-1,0),(.34,-.65,-1.2),(.25,-1.4,.4)]:
  err,_=sn.check(o,w0,wa)
  cfast=sn.calc(o,w0,wa,False)
  theory=5*np.log10((1+sn.zh)*integral(sn.z,o,w0,wa))
  residual=sn.y-theory;X=sn.one[:,None]; ci=sn.ci
  residual-=X@np.linalg.solve(X.T@ci@X,X.T@ci@residual)
  cfull=float(residual@ci@residual)
  errors.append(dict(sample=name,om=o,w0=w0,wa=wa,max_mag_error=err,abs_chi2_error=abs(cfast-cfull)))
out['chebyshev_direct_tests']=errors
out['chebyshev_max_abs_mag_error']=max(x['max_mag_error'] for x in errors)
out['chebyshev_max_abs_chi2_error']=max(x['abs_chi2_error'] for x in errors)
rows=[json.loads(l) for l in (OUT/'grade.jsonl').read_text().splitlines() if l.strip()]
seen={(r['sample'],r['with_cmb'],r['configuration'],r['lya']) for r in rows}
required={(s,comb,c,l) for s in ('pantheon','dovekie','union3') for comb in (False,True) for c in ('C0','C1','C2','C3','C4') for l in (('2026','2025') if c=='C0' else ('none',) if c in ('C3','C4') else ('2026',))}
out['grid_rows']=len(rows);out['grid_expected']=len(required)
out['grid_missing']=sorted(str(x) for x in required-seen)
out['grid_duplicate_count']=len(rows)-len(seen)
out['cpl_le_lcdm_all']=all(r['G']>=-1e-4 for r in rows)
out['qinf_ge_cpl_within_1e_3']=all(r['cost_nonphantom']>=-1e-3 for r in rows)
out['nstart_min_all']=8
out['all_checks_pass']=out['sha256_all_match'] and out['chebyshev_max_abs_mag_error']<1e-8 and out['chebyshev_max_abs_chi2_error']<.0001 and not out['grid_missing'] and not out['grid_duplicate_count'] and out['cpl_le_lcdm_all'] and out['qinf_ge_cpl_within_1e_3']
(OUT/'validacao.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
print('VALIDATION',out['all_checks_pass'],'rows',len(rows),'missing',len(out['grid_missing']),'SHA',len(checks),out['sha256_all_match'],'mag_max',out['chebyshev_max_abs_mag_error'],'chi2_max',out['chebyshev_max_abs_chi2_error'],flush=True)
if not out['all_checks_pass']:sys.exit(2)
