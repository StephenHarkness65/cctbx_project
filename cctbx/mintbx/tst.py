import sys, os
from cctbx.misc import python_utils
from cctbx_boost.arraytbx import shared
from cctbx_boost import sgtbx
from cctbx_boost import adptbx
from cctbx_boost import lbfgs
from cctbx_boost import mintbx
from cctbx import xutils
from cctbx.development import debug_utils
 
# XXX move to cctbx.minimization
def run_lbfgs(target_evaluator,
              min_iterations=10,
              max_calls=100,
              traditional_convergence_test=0):
  minimizer = lbfgs.minimizer(target_evaluator.n)
  if (traditional_convergence_test):
    is_converged = lbfgs.traditional_convergence_test(target_evaluator.n)
  else:
    is_converged = lbfgs.drop_convergence_test(min_iterations)
  try:
    while 1:
      x, f, g = target_evaluator()
      if (minimizer.run(x, f, g)): continue
      if (traditional_convergence_test):
        if (minimizer.iter() >= min_iterations and is_converged(x, g)): break
      else:
        if (is_converged(f)): break
      if (minimizer.nfun() > max_calls): break
      if (not minimizer.run(x, f, g)): break
  except RuntimeError, e:
    if (str(e).find("Tolerances may be too small.") < 0):
      raise
  return minimizer

class k_b_scaling_minimizer:

  def __init__(self, unit_cell, miller_indices, multiplicities,
               data_reference, data_scaled,
               k_initial, u_initial,
               refine_k, refine_u,
               min_iterations=50, max_calls=1000):
    python_utils.adopt_init_args(self, locals())
    self.anisotropic = hasattr(self.u_initial, "__len__")
    self.k_min = 1 # refine correction factor for k_initial
    self.u_scale = unit_cell.getLongestVector2()
    if (self.anisotropic):
      self.u_min = [u * self.u_scale for u in self.u_initial]
    else:
      self.u_min = self.u_initial * self.u_scale
    self.x = self.pack(self.k_min, self.u_min)
    self.n = self.x.size()
    self.minimizer = run_lbfgs(self, min_iterations, max_calls)
    self()
    del self.x
    self.k_min *= self.k_initial
    if (self.anisotropic):
      self.u_min = [u / self.u_scale for u in self.u_min]
    else:
      self.u_min /= self.u_scale

  def pack(self, k, u):
    v = []
    if (self.refine_k): v.append(k)
    if (self.refine_u):
      if (self.anisotropic): v += list(u)
      else:                  v.append(u)
    return shared.double(tuple(v))

  def unpack_x(self):
    i = 0
    if (self.refine_k):
      self.k_min = self.x[i]
      i += 1
    if (self.refine_u):
      if (self.anisotropic):
        self.u_min = self.x.as_tuple()[i:]
      else:
        self.u_min = self.x[i]

  def __call__(self):
    self.unpack_x()
    tg = mintbx.k_b_scaling_target_and_gradients(
      self.miller_indices, self.multiplicities,
      self.data_reference, self.data_scaled,
      self.k_initial * self.k_min, self.u_min, self.u_scale,
      self.refine_k, self.refine_u)
    self.f = tg.target()
    if (self.anisotropic):
      self.g = self.pack(tg.gradient_k(), tg.gradients_u_star())
    else:
      raise AssertionError, "Not implemented."
    return self.x, self.f, self.g

def exercise(SgInfo, d_min=2., verbose=0):
  elements = ("N", "C", "C", "O", "N", "C", "C", "O")
  friedel_flag = 0
  xtal = debug_utils.random_structure(
    SgInfo, elements,
    volume_per_atom=50.,
    min_distance=1.5,
    general_positions_only=0)
  print "Unit cell:", xtal.UnitCell
  print "Space group:", xtal.SgInfo.BuildLookupSymbol()
  miller_set = xutils.build_miller_indices(xtal, friedel_flag, d_min)
  multiplicity_set = xutils.reciprocal_space_array(miller_set,
    xtal.SgOps.multiplicity(miller_set.H, friedel_flag))
  f_ref = xutils.calculate_structure_factors(miller_set, xtal, abs_F=1)
  f_sca = xutils.reciprocal_space_array(miller_set, shared.double())
  k_sim = 1000
  u_star = [0.001,0.002,0.003,0.004,0.005,0.006]
  for i in xrange(len(miller_set.H)):
    h = miller_set.H[i]
    f_sca.F.push_back(
      k_sim * f_ref.F[i] * adptbx.DebyeWallerFactorUstar(h, u_star))
    if (0 or verbose): print h, f_ref.F[i], f_sca.F[i]
  k_min = 1
  u_min = [0,0,0,0,0,0]
  for p in xrange(20):
    for refine_k, refine_u in ((1,0), (0,1), (1,0), (0,1), (1,0), (1,1)):
      minimized = k_b_scaling_minimizer(
        xtal.UnitCell, miller_set.H, multiplicity_set.F, f_ref.F, f_sca.F,
        k_min, u_min,
        refine_k, refine_u)
      k_min = minimized.k_min
      u_min = minimized.u_min
  print "k_min:", minimized.k_min
  print "u_min:", minimized.u_min
  print "target:", minimized.f,
  print "after %d iteration(s)" % (minimized.minimizer.iter(),)
  print

def run():
  Flags = debug_utils.command_line_options(sys.argv[1:], (
    "RandomSeed",
    "AllSpaceGroups",
  ))
  if (not Flags.RandomSeed): debug_utils.set_random_seed(0)
  symbols_to_stdout = 0
  auto_test = 0
  if (len(sys.argv) > 1 + Flags.n):
    symbols = sys.argv[1:]
  else:
    symbols = debug_utils.get_test_space_group_symbols(Flags.AllSpaceGroups)
    symbols_to_stdout = 1
  if (len(sys.argv) == 1 or (Flags.AllSpaceGroups and len(sys.argv) == 2)):
    auto_test = 1
  for RawSgSymbol in symbols:
    if (RawSgSymbol.startswith("--")): continue
    SgSymbols = sgtbx.SpaceGroupSymbols(RawSgSymbol)
    SgInfo = sgtbx.SpaceGroup(SgSymbols).Info()
    LookupSymbol = SgInfo.BuildLookupSymbol()
    sys.stdout.flush()
    print >> sys.stderr, LookupSymbol
    sys.stderr.flush()
    if (symbols_to_stdout):
      print LookupSymbol
      sys.stdout.flush()
    exercise(SgInfo)
    sys.stdout.flush()

if (__name__ == "__main__"):
  run()
  t = os.times()
  print "u+s,u,s:", t[0] + t[1], t[0], t[1]
