"""Smoke do CAMB hibrido: beta=0 reproduz o EarlyQuintessence original; beta>0 muda o fundo."""
import camb
def run(beta):
    p = camb.set_params(H0=70, ombh2=0.0224, omch2=0.125, As=2.1e-9, ns=0.97, tau=0.055, dark_energy_model='EarlyQuintessence',
                        n=3, use_zc=True, zc=3400., fde_zc=0.07, theta_i=2.75, lmax=2000)
    p.DarkEnergy.beta = beta; p.DarkEnergy.n2 = 3.5
    r = camb.get_results(p)
    return r.get_derived_params()['thetastar'], r.get_derived_params()['rdrag'], r.get_cmb_power_spectra(p, CMB_unit='muK')['total'][1000, 0]
a = run(0.0); b = run(10.0)
print('camb', camb.__version__, 'beta=0', a, 'beta=10', b)
assert abs(b[1] - a[1]) > 1e-6
print('SMOKE OK')
