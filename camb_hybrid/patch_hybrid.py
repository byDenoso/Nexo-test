"""Patch do CAMB 1.6.6: potencial hibrido no EarlyQuintessence.
V = m^2 f^2 [ (1-cos t)^n + beta (1-cos t)^n2 ] + Lambda.  Com beta = 0 recupera exatamente o CAMB original.
Campos novos n2, beta logo apos min_steps_per_osc, no Fortran e no Python (mesma ordem)."""
import sys, pathlib
root = pathlib.Path(sys.argv[1])
f = root / 'fortran' / 'DarkEnergyQuintessence.f90'
s = f.read_text()
old_t = "        integer :: min_steps_per_osc = 10\n"
assert s.count(old_t) == 1
s = s.replace(old_t, old_t + "        real(dl) :: n2 = 3.5_dl !second power index (hybrid potential)\n        real(dl) :: beta = 0._dl !weight of the n2 term\n")
old_v = """    if (deriv==0) then
        V = units*this%m**2*this%f**2*(1 - cos(theta))**this%n + this%frac_lambda0*this%State%grhov
    else if (deriv ==1) then
        V = units*this%m**2*this%f*this%n*(1 - cos(theta))**(this%n-1)*sin(theta)
    else if (deriv ==2) then
        costheta = cos(theta)
        V = units*this%m**2*this%n*(1 - costheta)**(this%n-1)*(this%n*(1+costheta) -1)
    end if"""
new_v = """    costheta = cos(theta)
    if (deriv==0) then
        V = units*this%m**2*this%f**2*((1 - costheta)**this%n + this%beta*(1 - costheta)**this%n2) &
            + this%frac_lambda0*this%State%grhov
    else if (deriv ==1) then
        V = units*this%m**2*this%f*(this%n*(1 - costheta)**(this%n-1) + &
            this%beta*this%n2*(1 - costheta)**(this%n2-1))*sin(theta)
    else if (deriv ==2) then
        V = units*this%m**2*(this%n*(1 - costheta)**(this%n-1)*(this%n*(1+costheta) -1) + &
            this%beta*this%n2*(1 - costheta)**(this%n2-1)*(this%n2*(1+costheta) -1))
    end if"""
assert s.count(old_v) == 1
s = s.replace(old_v, new_v)
f.write_text(s)
p = root / 'camb' / 'dark_energy.py'
t = p.read_text()
old_p = '        ("min_steps_per_osc", c_int, "minimum number of steps per background oscillation scale"),\n'
assert t.count(old_p) == 1
t = t.replace(old_p, old_p + '        ("n2", c_double, "second power index of the hybrid potential"),\n        ("beta", c_double, "weight of the n2 term (0 = original potential)"),\n')
p.write_text(t)
print('patch ok')
