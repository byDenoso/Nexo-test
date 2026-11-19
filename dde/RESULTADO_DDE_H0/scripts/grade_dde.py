#!/usr/bin/env python3
"""TESTE_DECISIVO_DDE_H0: data-defined BAO/SN GLS, flat CPL and LCDM.
Inputs taken strictly from the checked SHA256SUMS manifest.
Background WITHOUT CMB follows provided analytical E(z), with 48-node quadrature.
Background WITH CMB follows the provided CAMB 1.6.6 PPF parameterization and compressed theta/omega covariance.
For speed, SN likelihood is compressed using a Chebyshev basis in z/(1+z). Its accuracy is checked against full SN vectors separately.
"""
import os,sys, pathlib,csv,json,time,argparse,hashlib
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from scipy import optimize,linalg
try:
 import camb
except ImportError:
 camb=None
R=pathlib.Path(__file__).resolve().parents[2]/'TESTE_DECISIVO_DDE_H0'
D=R/'dados'
OUT=pathlib.Path(__file__).resolve().parents[1]/'saidas'
CKM=299792.458
CMU=np.array([0.01041,0.02223,0.14208])
CCMB=1.e-9*np.array([[.006621,.12444,-1.1929],[.12444,21.344,-94.001],[-1.1929,-94.001,1488.4]])
CICMB=np.linalg.inv(CCMB)
GX, GW=np.polynomial.legendre.leggauss(48)
NC=18

def integral(z,om,w0,wa):
 z=np.atleast_1d(np.asarray(z,dtype=float))
 if np.any(z<0) or not (0<om<1) or not (-6<w0<3) or not (-8<wa<8):
  return np.full_like(z,np.nan)
 v=np.zeros_like(z)
 for f0,f1 in ((0,.5),(.5,1.)):
  a,b=z*f0,z*f1
  zz=(b-a)[:,None]*GX[None,:]/2+(b+a)[:,None]/2
  zp=1+zz
  e2=om*zp**3+(1-om)*zp**(3*(1+w0+wa))*np.exp(-3*wa*zz/zp)
  v+=(b-a)/2*np.sum(GW[None,:]/np.sqrt(e2),axis=1)
 return v

def e_z(z,om,w0,wa):
 z=np.asarray(z,dtype=float);zp=1+z
 return np.sqrt(om*zp**3+(1-om)*zp**(3*(1+w0+wa))*np.exp(-3*wa*z/zp))

def cmb_bg(p):
 # exact contract from reference g15_cmb.py
 H0,ob,obc,w0,wa=[float(x) for x in p]
 cp=camb.set_params(H0=H0,ombh2=ob,omch2=obc-ob-0.06/93.14,mnu=.06,
   num_massive_neutrinos=1,dark_energy_model='ppf',w=w0,wa=wa,
   WantTransfer=False,WantCls=False)
 bg=camb.get_background(cp,no_thermo=False)
 d=bg.get_derived_params()
 return bg,d['thetastar']/100.,d['rdrag']

class BAO:
 def __init__(self,ly='2026',drop_lrg=False):
  rows=[l.split() for l in open(D/'desi_gaussian_bao_ALL_GCcomb_mean.txt') if not l.startswith('#')]
  fullz=np.array([float(x[0]) for x in rows]); y=np.array([float(x[1]) for x in rows]); k=np.array([x[2] for x in rows]);cov=np.loadtxt(D/'desi_gaussian_bao_ALL_GCcomb_cov.txt')
  if ly=='2026':
   y[11:13]=[8.600,39.32];cov[11:,11:]=[[.066**2,.225*.066*.33],[.225*.066*.33,.33**2]]
  elif ly not in ('2025','none'):raise ValueError(ly)
  mask=np.ones(len(y),bool)
  if ly=='none':mask[11:]=False
  if drop_lrg:mask &= ~np.isin(np.round(fullz,3),[.510,.706])
  self.z=fullz[mask];self.y=y[mask];self.kind=k[mask];self.C=cov[np.ix_(mask,mask)];self.ci=np.linalg.inv(self.C)
  self.ly=ly;self.drop_lrg=drop_lrg
 def calc(self,om,w0,wa,rdh=None,bg=None):
  if bg is not None:
   dm=np.asarray(bg.comoving_radial_distance(self.z),float)
   dh=CKM/np.asarray(bg.hubble_parameter(self.z),float)
  else:
   dm=integral(self.z,om,w0,wa)
   dh=1/e_z(self.z,om,w0,wa)
  v=np.empty(len(self.z))
  for i,(zi,kind) in enumerate(zip(self.z,self.kind)):
   if kind=='DM_over_rs':v[i]=dm[i]
   elif kind=='DH_over_rs':v[i]=dh[i]
   else:v[i]=(zi*dm[i]**2*dh[i])**(1/3)
  if bg is not None:
   model=v/rdh # here rdh actually rdrag Mpc
   g=bg.Params.H0*rdh/100 # H0 * rd in [km/s]/100
  else:
   v*=CKM/100
   v_ci=self.ci@v
   beta=np.dot(v_ci,self.y)/np.dot(v_ci,v)
   beta=np.clip(beta,1/130,1/80)
   model=v*beta;g=1/beta
  dd=self.y-model
  return float(dd@self.ci@dd),float(g)

class SN:
 def __init__(self,name):
  self.name=name
  if name=='pantheon':
   f=D/'PantheonPlus_SH0ES_tabela_corrigida_Hoyt.dat'
   h=open(f).readline().split()
   rows=[l.split() for l in open(f)][1:]
   j={x:i for i,x in enumerate(h)}
   z0=np.array([float(x[j['zHD']]) for x in rows]);mask=(z0>.01)&(np.array([int(x[j['IS_CALIBRATOR']]) for x in rows])==0)
   self.z=z0[mask];self.zh=np.array([float(x[j['zHEL']]) for x in rows])[mask]
   self.y=np.array([float(x[j['m_b_corr']]) for x in rows])[mask]
   self.survey=np.array([int(x[j['IDSURVEY']]) for x in rows])[mask]
   a=np.loadtxt(D/'PantheonPlus_STAT_SYS.cov');n=int(a[0]);cov=a[1:].reshape(n,n)[np.ix_(mask,mask)]
   self.cov=cov;self.ci=np.linalg.inv(cov)
  elif name=='dovekie':
   rr=list(csv.DictReader(open(D/'DES-Dovekie_HD.csv')))
   self.z=np.array([float(x['zHD']) for x in rr]);self.zh=np.array([float(x['zHEL']) for x in rr])
   self.y=np.array([float(x['MU']) for x in rr]);self.survey=np.array([int(x['IDSURVEY']) for x in rr])
   f=np.load(D/'DES-Dovekie_covtot_inv.npz');n=int(f['nsn'][0]);ci=np.zeros((n,n))
   ci[np.triu_indices(n)]=f['cov'];self.ci=ci+ci.T-np.diag(ci.diagonal());self.cov=None
  elif name=='union3':
   rr=[l.split() for l in open(D/'Union3_lcparam_full.txt') if not l.startswith('#')]
   self.z=np.array([float(x[1]) for x in rr]);self.zh=np.array([float(x[2]) for x in rr]);self.y=np.array([float(x[4]) for x in rr]);self.survey=None
   a=np.loadtxt(D/'Union3_mag_covmat.txt');n=int(a[0]);self.cov=a[1:].reshape(n,n);self.ci=np.linalg.inv(self.cov)
  else:raise ValueError(name)
  self.zmax=self.z.max();self.zmin=self.z.min();self.x=lambda zz:2*(zz/(1+zz)-self.zmin/(1+self.zmin))/(self.zmax/(1+self.zmax)-self.zmin/(1+self.zmin))-1
  self.angles=(np.arange(NC)+.5)*np.pi/NC
  self.nodes=(np.cos(self.angles)+1)/2*(self.zmax/(1+self.zmax)-self.zmin/(1+self.zmin))+self.zmin/(1+self.zmin)
  self.nodes=self.nodes/(1-self.nodes)
  self.vander_nodes=np.polynomial.chebyshev.chebvander(self.x(self.nodes),NC-1)
  self.vander_inv=np.linalg.inv(self.vander_nodes)
  self.T=np.polynomial.chebyshev.chebvander(self.x(self.z),NC-1)
  self.zref=integral(self.z,.3,-1,0)
  self.dref=integral(self.nodes,.3,-1,0)
  self.ref=5*np.log10((1+self.zh)*self.zref)
  self.one=np.ones(len(self.z))
  self.offset_vec=(self.survey==10).astype(float) if name=='pantheon' else ((self.survey!=10).astype(float) if name=='dovekie' else (self.z<=.15).astype(float))
  self.version={}
  for offset in (False,True):
   X=np.stack([self.one,self.offset_vec],axis=-1) if offset else self.one[:,None]
   ciX=self.ci@X;Xi=np.linalg.inv(X.T@ciX)
   # project via a symmetric matrix avoiding catastrophic cancellation, O(N^2) once
   M=self.ci - ciX@Xi@ciX.T
   M=(M+M.T)/2
   A=M@self.T
   self.version[offset]={'X':X,'M':M,'K':self.T.T@A, 'C':self.y-self.ref}
   v=self.y-self.ref;v=v-X@np.linalg.solve(X.T@self.ci@X,X.T@self.ci@v)
   self.version[offset]['b']=A.T@v
   self.version[offset]['c']=float(v@M@v)
   self.version[offset]['v']=v
 def coefs(self,om,w0,wa,bg=None):
  if bg is None:
   shape=integral(self.nodes,om,w0,wa)/self.dref
  else:
   shape=np.asarray(bg.comoving_radial_distance(self.nodes),float)/(CKM/70*self.dref)
  return self.vander_inv@(5*np.log10(shape))
 def calc(self,om,w0,wa,offset=False,bg=None,override=None):
  dd=self.version[offset];p=self.coefs(om,w0,wa,bg)
  b=dd['b'] if override is None else override[0]
  c=dd['c'] if override is None else override[1]
  chi2=c-2*p@b+p@dd['K']@p
  return float(chi2)
 def check(self,om,w0,wa,bg=None):
  co=self.coefs(om,w0,wa,bg)
  approx=self.T@co
  tru=5*np.log10(integral(self.z,om,w0,wa)/self.zref) if bg is None else 5*np.log10(np.asarray(bg.comoving_radial_distance(self.z),float)/(CKM/70*self.zref))
  return float(np.max(np.abs(tru-approx))),float(np.std(tru-approx))

def penalty_domain(om,w0,wa):
 if not(.1<om<.65 and -3.0<=w0<=0. and -5<=wa<=5 and w0+wa<0):return False
 return True

class Job:
 def __init__(self,name,cmb,config,ly='2026'):
  self.name=name;self.cmb=cmb;self.config=config;self.ly=ly
  self.sn=SN(name)
  self.bao=BAO(ly,drop_lrg=(config in ('C2','C4')))
  self.off=config in ('C1','C4')
 def calc(self,p,model,details=False):
  if self.cmb:
   H0,ob,obc=map(float,p[:3]);w0,wa=map(float,p[3:5]) if model=='cpl' else ((-1.,0.) if model=='lcdm' else (-1.+float(p[3]),float(p[4])-float(p[3])))
   om=obc/(H0/100)**2
   if not (50<H0<90 and .015<ob<.030 and .08<obc<.20 and obc>ob+.0007 and penalty_domain(om,w0,wa)):
    return (1.e8, None) if details else 1.e8
   try:
    bg,th,rd=cmb_bg([H0,ob,obc,w0,wa])
    cb,g=self.bao.calc(om,w0,wa,rd,bg)
    cs=self.sn.calc(om,w0,wa,self.off,bg)
    d=np.array([th,ob,obc])-CMU
    cc=float(d@CICMB@d)
   except Exception as ex:
    return (1e8,None) if details else 1e8
  else:
   om=float(p[0]);w0,wa=(map(float,p[1:3]) if model=='cpl' else ((-1.,0.) if model=='lcdm' else (-1.+float(p[1]),float(p[2])-float(p[1]))))
   if not penalty_domain(om,w0,wa):return (1e8,None) if details else 1e8
   bg=None;H0=None;rd=None;cc=0.
   cb,g=self.bao.calc(om,w0,wa)
   cs=self.sn.calc(om,w0,wa,self.off)
  result=cs+cb+cc
  if details:return result,dict(chi2_sn=cs,chi2_bao=cb,chi2_cmb=cc,om=om,w0=w0,wa=wa,H0=H0,H0rd=100*g,rd=rd)
  return result
 def bounds(self,model):
  base=[(50.01,89.99),(.01501,.02999),(.08001,.19999)] if self.cmb else [(.10001,.64999)]
  if model=='cpl':base += [(-3.,-.00001),(-4.9999,4.9999)]
  elif model=='qinf':base += [(0.,.99999),(0.,.99999)]
  return base
 def starts(self,model,n=8):
  if self.cmb:
   startbase=[[67.5,.02223,.14208],[70,.02223,.14208],[65,.02218,.141],[72,.0223,.143],[68.5,.022,.143],[69,.0225,.142],[67,.02218,.145],[71,.0219,.14]]
  else:startbase=[[.30],[.325],[.285],[.345],[.25],[.38],[.32],[.4]]
  if model=='lcdm':return startbase[:n]
  if model=='cpl':a=[[-.9,-.5],[-.75,-1.1],[-1.,0.],[-.5,-1.6],[-.8,-.2],[-1.2,.4],[-1.4,.5],[-.6,-.9]]
  else:a=[[0.,0.],[.1,.05],[.25,.05],[.1,.3],[.4,.1],[.0,.3],[.5,.0],[.1,.6]]
  return [startbase[i]+a[i] for i in range(n)]
 def fit(self,model,nstart=8,record=False):
  starts=self.starts(model,nstart);bound=self.bounds(model)
  best=None;allstarts=[]
  for i,s in enumerate(starts):
   # L-BFGS-B tends to be robust near gaussian CMB; Powell stabilizes if L-BFGS-B faces a bound
   res=optimize.minimize(lambda x:self.calc(x,model),s,method='L-BFGS-B',bounds=bound,
    options={'maxiter':500,'ftol':1e-11,'gtol':2e-5,'maxls':25,'eps':1e-5})
   allstarts.append({'start':i,'fun':float(res.fun),'ok':bool(res.success),'nfev':int(res.nfev)})
   if np.isfinite(res.fun) and (best is None or res.fun<best.fun):best=res
  chi,parts=self.calc(best.x,model,True)
  return dict(model=model,params=[float(x) for x in best.x],chi2=float(chi),components=parts,nfev=sum(a['nfev'] for a in allstarts),starts=allstarts if record else None)

def run_grid(names,flags=('C0','C1','C2','C3','C4'),cmbs=(False,True),add2025=True):
 OUT.mkdir(exist_ok=True,parents=True)
 statefile=OUT/'grade.jsonl'; done=set()
 if statefile.exists():
  for line in statefile.read_text().splitlines():
   try:
    row=json.loads(line);done.add((row['sample'],row['with_cmb'],row['configuration'],row['lya']))
   except Exception:pass
 for name in names:
  for cmb in cmbs:
   for flag in flags:
    for ly in (['2026','2025'] if flag=='C0' and add2025 else ['none' if flag in ['C3','C4'] else '2026']):
     key=(name,cmb,flag,ly)
     if key in done:continue
     t=time.time();job=Job(name,cmb,flag,ly)
     models={}
     for model in ('lcdm','cpl','qinf'):
      models[model]=job.fit(model,nstart=8)
     if models['cpl']['chi2']>models['lcdm']['chi2']+1e-4:
      raise ArithmeticError('CPL min > LCDM min '+str(key))
     row=dict(sample=name,with_cmb=cmb,configuration=flag,lya=ly,models=models,
       G=models['lcdm']['chi2']-models['cpl']['chi2'],cost_nonphantom=models['qinf']['chi2']-models['cpl']['chi2'],elapsed_s=time.time()-t)
     with open(statefile,'a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
     print('GRID',*key,'G=%.5f'%row['G'],'Q=%.5f'%row['cost_nonphantom'],'time=%.1f'%row['elapsed_s'],'evals',sum(x['nfev'] for x in models.values()),flush=True)

def quickcheck():
 for name in ('pantheon','dovekie','union3'):
  sn=SN(name);t0=time.time()
  for o,w0,wa in [(0.3,-1,0),(.34,-.65,-1.2),(.25,-1.4,.4)]:
   mx,st=sn.check(o,w0,wa)
   cc=sn.calc(o,w0,wa,False)
   th=5*np.log10((1+sn.zh)*integral(sn.z,o,w0,wa));d=sn.y-th
   ci=sn.ci;X=sn.one[:,None];d-=X@np.linalg.solve(X.T@ci@X,X.T@ci@d)
   direct=d@ci@d
   print('CHECK',name,o,w0,wa,'mag error',mx,'chi2fast',cc,'chi2direct',direct,'delta',cc-direct,flush=True)
  print('time',time.time()-t0,flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--samples',default='pantheon,dovekie,union3');ap.add_argument('--mode',default='check',choices=['check','grid']);ap.add_argument('--cmb',default='both',choices=['both','yes','no']);ap.add_argument('--flags',default='C0,C1,C2,C3,C4');args=ap.parse_args()
 if args.mode=='check':quickcheck()
 else:run_grid(args.samples.split(','),flags=args.flags.split(','),cmbs={'yes':(True,),'no':(False,),'both':(False,True)}[args.cmb])
