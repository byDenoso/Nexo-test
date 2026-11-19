#!/usr/bin/env python3
"""Pantheon+ + DESI DR2, ruler prior, BBN omega_b (independent normalized nuisance)."""
import json, pathlib,sys
import numpy as np
from scipy import optimize
from grade_dde import SN,BAO,integral,e_z,CKM,OUT

rows=[json.loads(x) for x in open(OUT/'grade.jsonl')]
source={(a['configuration'],a['models']['lcdm']['model']):a for a in rows if a['sample']=='pantheon' and not a['with_cmb'] and a['lya']=='2026'}
sn=SN('pantheon');bao=BAO('2026')
R_S=144.3;R_ERR=1.5;R_REF=147.09
all_results=[]
for config in ('C0','C1'):
 for model in ('lcdm','cpl'):
  row=source[(config,'lcdm')]
  m=row['models'][model];p0=m['components']
  is_cpl=model=='cpl';is_offset=config=='C1';v0=np.array([p0['om'],p0['w0'],p0['wa'],p0['H0rd']/100])
  def calc(q):
   if is_cpl:
    om=.3+.1*q[0];w0=-1+.5*q[1];wa=q[2];g=100+10*q[3]
   else:
    om=.3+.1*q[0];w0=-1;wa=0;g=100+10*q[1]
   if not(.1<om<.65 and -3<=w0<=0 and -5<=wa<=5 and w0+wa<0 and 80<g<130):return 1.e8
   z=bao.z;dm=integral(z,om,w0,wa);dh=1/e_z(z,om,w0,wa)
   sh=np.array([dm[i] if kind=='DM_over_rs' else dh[i] if kind=='DH_over_rs' else (z[i]*dm[i]**2*dh[i])**(1/3) for i,kind in enumerate(bao.kind)])
   r=bao.y-(CKM/100)*sh/g
   return float(sn.calc(om,w0,wa,is_offset)+r@bao.ci@r)
  init=np.array([(v0[0]-.3)/.1, (v0[1]+1)/.5, v0[2], (v0[3]-100)/10] if is_cpl else [(v0[0]-.3)/.1,(v0[3]-100)/10])
  res=optimize.minimize(calc,init,method='BFGS',options={'gtol':1e-5,'maxiter':500})
  x=res.x;n=len(x)
  steps=np.array([5e-4,5e-4,8e-4,3e-4] if is_cpl else [5e-4,3e-4])
  H=np.zeros((n,n))
  for i in range(n):
   ei=np.zeros(n);ei[i]=steps[i]
   H[i,i]=(calc(x+ei)-2*calc(x)+calc(x-ei))/steps[i]**2
   for j in range(i):
    ej=np.zeros(n);ej[j]=steps[j]
    H[i,j]=H[j,i]=(calc(x+ei+ej)-calc(x+ei-ej)-calc(x-ei+ej)+calc(x-ei-ej))/(4*steps[i]*steps[j])
  cov=2*np.linalg.inv(H)
  idx=-1;sigma_g=float(np.sqrt(cov[idx,idx])*10);g=100+10*x[idx]
  if res.fun - m['chi2'] >.01: raise ArithmeticError('H0 best mismatch '+str((config,model,res.fun,m['chi2'])))
  out=dict(config=config,model=model,chi2=float(res.fun),om=float(.3+.1*x[0]),w0=float(-1+.5*x[1]) if is_cpl else -1,wa=float(x[2]) if is_cpl else 0,
   g_h_rd=float(g),g_sigma=sigma_g,omega_b_bbn=.02218,omega_b_bbn_sigma=.00055,
   rd_prior_mean=R_S,rd_prior_sigma=R_ERR,rd_fixed=R_REF)
  for typ,rd,srd in [('free_prior',R_S,R_ERR),('fixed',R_REF,0)]:
   h0=100*g/rd
   sh=np.hypot(100*sigma_g/rd,100*g*srd/rd**2)
   out[typ]=dict(H0_kmsMpc=float(h0),sigma_H0=float(sh),SH0ES_sigma=float(abs(h0-73.04)/np.hypot(sh,1.04)))
  print(out,flush=True)
  all_results.append(out)
(OUT/'h0_ruler.json').write_text(json.dumps(all_results,indent=2,ensure_ascii=False)+'\n')
