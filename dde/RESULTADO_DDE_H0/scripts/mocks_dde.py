#!/usr/bin/env python3
"""Parametric Gaussian mocks with identical C0--C4 refitting; resumable.
Runs CAMB 1.6.6 per objective, with 8 independent minimization starts per model.
Example: python mocks_dde.py --sample union3 --truth lcdm --n 1000 --seed 2026111901
No synthetic p-values: only completed successful mocks enter add-one counts.
"""
import os,json,pathlib,time,hashlib,argparse
import numpy as np
from scipy.linalg import solve_triangular
import grade_dde as mod
from grade_dde import SN,BAO,Job,OUT,CKM,cmb_bg,CCMB

OUT.mkdir(parents=True,exist_ok=True)
SRC=OUT/'grade.jsonl'

def make_job(sn,flag):
 j=Job.__new__(Job)
 j.name=sn.name;j.cmb=True;j.config=flag
 j.ly='none' if flag in ('C3','C4') else '2026'
 j.sn=sn;j.bao=BAO(j.ly,drop_lrg=flag in ('C2','C4'))
 j.off=flag in ('C1','C4')
 return j

def predicted_bao(bao,bg,rd):
 z=bao.z;dm=bg.comoving_radial_distance(z);dh=CKM/bg.hubble_parameter(z)
 v=[]
 for i,k in enumerate(bao.kind):
  v.append(dm[i] if k=='DM_over_rs' else dh[i] if k=='DH_over_rs' else (z[i]*dm[i]**2*dh[i])**(1/3))
 return np.asarray(v)/rd

def update_sne_mocks(sn,ymock):
 # Constant shifts are fully projected; subtract before matrix products for stability.
 r=ymock-sn.ref;r=r-r.mean()
 for offset in (False,True):
  d=sn.version[offset];Mr=d['M']@r
  d['b']=sn.T.T@Mr;d['c']=float(r@Mr)

def load_grids(name):
 rows=[json.loads(q) for q in open(SRC)]
 hits=[q for q in rows if q['sample']==name and q['with_cmb'] and q['configuration']=='C0' and q['lya']=='2026']
 if len(hits)!=1:raise ValueError('need one C0 CMB grid fit for '+name)
 return hits[0]

def run(name,truth,N,seed):
 grid=load_grids(name)
 s=SN(name);jobs={c:make_job(s,c) for c in ('C0','C1','C2','C3','C4')}
 real={x['configuration']:x for x in (json.loads(z) for z in open(SRC)) if x['sample']==name and x['with_cmb'] and x['lya'] in ('2026','none')}
 if set(real)!=set(jobs):raise ValueError('complete grid required to measure search statistic')
 G_obs={k:real[k]['G'] for k in jobs}
 T_obs=max((G_obs['C0']-G_obs[k])/G_obs['C0'] for k in ('C1','C2','C3'))
 true=grid['models'][truth]['params']
 if truth=='lcdm':H0,ob,obc=true;w0,wa=-1.,0.
 else:H0,ob,obc,w0,wa=true
 bg,theta,rd=cmb_bg([H0,ob,obc,w0,wa]);om=obc/(H0/100)**2
 mu_pred=s.ref+s.T@s.coefs(om,w0,wa,bg)
 bao_full=BAO('2026',False);bao_pred=predicted_bao(bao_full,bg,rd)
 nu=np.array([theta,ob,obc]);lcmb=np.linalg.cholesky(CCMB);lbao=np.linalg.cholesky(bao_full.C)
 if s.cov is not None:
  lsn=np.linalg.cholesky(s.cov)
  def noise_sn(rng):return lsn@rng.standard_normal(len(s.z))
 else:
  L=np.linalg.cholesky(s.ci)
  def noise_sn(rng):return solve_triangular(L.T,rng.standard_normal(len(s.z)),lower=False)
 original_i=[]
 fullkey=[(z,k) for z,k in zip(bao_full.z,bao_full.kind)]
 for j in jobs.values():
  ids=[fullkey.index((z,k)) for z,k in zip(j.bao.z,j.bao.kind)]
  original_i.append((j,ids))
 outfile=OUT/('mock_'+name+'_'+truth+'.jsonl')
 done=[]
 if outfile.exists():
  for row in outfile.read_text().splitlines():
   try:done.append(json.loads(row)['mock_id'])
   except Exception:pass
 rng=np.random.default_rng(seed)
 print('START',name,truth,'N',N,'seed',seed,'existing',len(done),'T_obs',T_obs,flush=True)
 for i in range(N):
  snnoise=noise_sn(rng);baonoise=lbao@rng.standard_normal(len(bao_pred));cmbnoise=lcmb@rng.standard_normal(3)
  if i in done:continue
  tic=time.time()
  update_sne_mocks(s,mu_pred+snnoise)
  z_bao=bao_pred+baonoise
  mod.CMU=nu+cmbnoise
  for j,ids in original_i:j.bao.y=z_bao[ids]
  fits={}
  for key,j in jobs.items():
   fl=j.fit('lcdm',nstart=8)
   fc=j.fit('cpl',nstart=8)
   if fc['chi2']>fl['chi2']+1e-6:
    # the nested model MUST be included and the physical optimizer checked
    bounds=j.bounds('cpl')
    x0=fl['params']+[-1.,0.]
    from scipy.optimize import minimize
    resc=minimize(lambda p:j.calc(p,'cpl'),x0,method='L-BFGS-B',bounds=bounds,
         options={'ftol':1e-11,'gtol':2e-5,'maxiter':500,'eps':1e-5})
    if resc.fun<fc['chi2']:fc['chi2']=float(resc.fun);fc['params']=list(map(float,resc.x))
   if fc['chi2']>fl['chi2']+1e-4:raise ArithmeticError('CPL > LCDM '+str((name,truth,i,key,fl['chi2'],fc['chi2'])))
   fits[key]={'lcdm':fl['chi2'],'cpl':fc['chi2'],'G':max(0.,fl['chi2']-fc['chi2']),
      'lcdm_evals':fl['nfev'],'cpl_evals':fc['nfev']}
  gc=fits['C0']['G'];T=(max((gc-fits[k]['G'])/gc for k in ('C1','C2','C3')) if gc>1e-10 else 0.)
  result={'sample':name,'truth':truth,'seed':seed,'mock_id':i,'G':fits,'search_drop_relative':T,'elapsed_s':time.time()-tic}
  with open(outfile,'a') as f:f.write(json.dumps(result)+'\n')
  print('FINISH',name,truth,'id',i,'G0',gc,'T',T,'elapsed',result['elapsed_s'],flush=True)
 # On completion or interruption, only completed draws are counted.
 rows=[json.loads(l) for l in outfile.read_text().splitlines() if l.strip()]
 rows=[x for x in rows if x['mock_id']<N]
 kvals={}
 if truth=='lcdm':
  for c in ('C0','C1','C4'):
   k=sum(x['G'][c]['G']>=G_obs[c] for x in rows)
   kvals[c]={'k':k,'N':len(rows),'p_add_one':(k+1)/(len(rows)+1)}
 else:
  k=sum(x['search_drop_relative']>=T_obs for x in rows)
  kvals={'pattern':{'k':k,'N':len(rows),'p_add_one':(k+1)/(len(rows)+1)}}
 out={'sample':name,'truth':truth,'seed':seed,'n_target':N,'n_complete':len(rows),'G_observed':G_obs,'T_observed':T_obs,'p_values':kvals}
 (OUT/('mock_summary_'+name+'_'+truth+'.json')).write_text(json.dumps(out,indent=2)+'\n')
 print('SUMMARY',json.dumps(out),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sample',choices=['pantheon','dovekie','union3'],required=True);p.add_argument('--truth',choices=['lcdm','cpl'],required=True);p.add_argument('--n',type=int,default=1000);p.add_argument('--seed',type=int,default=2026111901);a=p.parse_args()
 run(a.sample,a.truth,a.n,a.seed)
