from __future__ import division

import sys,os
from libtbx.utils import Sorry
from cctbx.array_family import flex
from copy import deepcopy

from cctbx.array_family import flex
import scitbx.lbfgs
import libtbx.utils

def write_mtz(ma=None,phases=None,file_name=None):
  mtz_dataset=ma.as_mtz_dataset(column_root_label="FWT")
  mtz_dataset.add_miller_array(miller_array=phases,column_types="P", column_root_label="PHWT")
  mtz_dataset.mtz_object().write(file_name=file_name)

def get_means(d_min,d_max,ma,n_bins):
  ma.setup_binner(n_bins=n_bins,d_max=d_max,d_min=d_min)
  binner=ma.binner()
  mean_f=[]
  bin_d_min=[]
  for bin in list(binner.range_used()):
    bin_d_min.append(binner.bin_d_min(bin))
    sele=ma.binner().selection(bin)
    mean_f.append(ma.select(sele).data().min_max_mean().mean)
  return mean_f,bin_d_min


# XXX copied these from cctbx.miller; made small change to catch weird case
#  where normalizations are negative.  Just multiply these *-1 and it seems to
#  close to what we want. Figure this out later...
# XXX Also set means=1 not mean square = 1

def amplitude_quasi_normalisations(ma, d_star_power=1, set_to_minimum=None):
    epsilons = ma.epsilons().data().as_double()
    mean_f_sq_over_epsilon = flex.double()
    for i_bin in ma.binner().range_used():
      sel = ma.binner().selection(i_bin)
      #sel_f_sq = flex.pow2(ma.data().select(sel))
      sel_f_sq = ma.data().select(sel)
      if (sel_f_sq.size() > 0):
        sel_epsilons = epsilons.select(sel)
        sel_f_sq_over_epsilon = sel_f_sq / sel_epsilons
        mean_f_sq_over_epsilon.append(flex.mean(sel_f_sq_over_epsilon))
      else:
        mean_f_sq_over_epsilon.append(0)
    mean_f_sq_over_epsilon_interp = ma.binner().interpolate(
      mean_f_sq_over_epsilon, d_star_power)
    if set_to_minimum and not mean_f_sq_over_epsilon_interp.all_gt(0):
      # HACK NO REASON THIS SHOULD WORK
      sel = (mean_f_sq_over_epsilon_interp <= set_to_minimum)
      mean_f_sq_over_epsilon_interp.set_selected(sel,-mean_f_sq_over_epsilon_interp)
      sel = (mean_f_sq_over_epsilon_interp <= set_to_minimum)
      mean_f_sq_over_epsilon_interp.set_selected(sel,set_to_minimum)
    assert mean_f_sq_over_epsilon_interp.all_gt(0)
    from cctbx.miller import array
    #return array(ma, flex.sqrt(mean_f_sq_over_epsilon_interp))
    return array(ma, mean_f_sq_over_epsilon_interp)

def quasi_normalize_structure_factors(ma, d_star_power=1, set_to_minimum=None):
    normalisations = amplitude_quasi_normalisations(ma, d_star_power,
       set_to_minimum=set_to_minimum)
    q = ma.data() / normalisations.data()
    from cctbx.miller import array
    return array(ma, q)

def get_array(file_name=None,labels=None):

  print "Reading from %s" %(file_name)
  from iotbx import reflection_file_reader
  reflection_file = reflection_file_reader.any_reflection_file(
       file_name=file_name)
  array_to_use=None
  if labels:
    for array in reflection_file.as_miller_arrays():
      if ",".join(array.info().labels)==labels:
        array_to_use=array
        break
  else:
    for array in reflection_file.as_miller_arrays():
      if array.is_complex_array() or array.is_xray_amplitude_array() or\
          array.is_xray_intensity_array():
        array_to_use=array
        break
  if not array_to_use:
    text=""
    for array in reflection_file.as_miller_arrays():
      text+=" %s " %(",".join(array.info().labels))

    raise Sorry("Cannot identify array to use...possibilities: %s" %(text))

  print "Using the array %s" %(",".join(array_to_use.info().labels))
  return array_to_use


def get_amplitudes(args):
  if not args or 'help' in args or '--help' in args:
    print "\nsharpen.py"
    print "Read in map coefficients or amplitudes and sharpen"
    return

  new_args=[]
  file_name=None
  for arg in args:
    if os.path.isfile(arg) and arg.endswith(".mtz"):
      file_name=arg
    else:
      new_args.append(arg)
  args=new_args
  labels=None

  array_list=[]
  d_min=None
  d_max=None
  b_iso=None

  array_list.append(get_array(file_name=file_name,labels=labels))
  array=array_list[-1]
  phases=None
  assert array.is_complex_array()
  return array


def adjust_amplitudes_linear(f_array,b1,b2,b3,d_cut=None):
  # do something to the amplitudes.
  #   b1=delta_b at midway between d=inf and d=d_cut,b2 at d_cut,
  #   b3 at d_min (added to b2)
  # pseudo-B at position of b1= -b1/sthol2_2= -b1*4*d_cut**2
  #  or...b1=-pseudo_b1/(4*d_cut**2)
  #  typical values of say b1=1 at 3 A -> pseudo_b1=-4*9=-36

  data_array=f_array.data()
  sthol2_array=f_array.sin_theta_over_lambda_sq()
  scale_array=flex.double()
  import math
  d_min=f_array.d_min()

  sthol2_2=0.25/d_cut**2
  sthol2_1=sthol2_2*0.5
  sthol2_3=0.25/d_min**2
  b0=0.0
  d_spacings=f_array.d_spacings()
  b3_use=b3+b2
  for x,(ind,sthol2),(ind1,d) in zip(data_array,sthol2_array,d_spacings):
      if sthol2 > sthol2_2:
        value=b2+(sthol2-sthol2_2)*(b3_use-b2)/(sthol2_3-sthol2_2)
      elif sthol2 > sthol2_1:
        value=b1+(sthol2-sthol2_1)*(b2-b1)/(sthol2_2-sthol2_1)
      else:
        value=b0+(sthol2-0.)*(b1-b0)/(sthol2_1-0.)
      scale_array.append(math.exp(value))
  data_array=data_array*scale_array
  return f_array.customized_copy(data=data_array)

def calculate_map(map_coeffs=None,crystal_symmetry=None,n_real=None):
    if crystal_symmetry is None: crystal_symmetry=map_coeffs.crystal_symmetry()
    # And get new map
    from cctbx import maptbx
    from cctbx.maptbx import crystal_gridding
    if n_real:
      cg=crystal_gridding(
        unit_cell=crystal_symmetry.unit_cell(),
        space_group_info=crystal_symmetry.space_group_info(),
        pre_determined_n_real=n_real)
    else:
      cg=None
    fft_map = map_coeffs.fft_map( resolution_factor = 0.25,
       crystal_gridding=cg,
       symmetry_flags=maptbx.use_space_group_symmetry)
    fft_map.apply_sigma_scaling()
    map_data=fft_map.real_map_unpadded()
    return map_data

def get_sharpened_map(ma,phases,b,d_cut):
  sharpened_ma=adjust_amplitudes_linear(ma,b[0],b[1],b[2],d_cut=d_cut)
  new_map_coeffs=sharpened_ma.phase_transfer(phase_source=phases,deg=True)
  return calculate_map(map_coeffs=new_map_coeffs)


def calculate_adjusted_sa(ma,phases,b,
    d_cut=None,
    solvent_fraction=None,
    region_weight=None,
    sa_percent=None,
    fraction_occupied=None,
    use_sg_symmetry=None,):

  map_data=get_sharpened_map(ma,phases,b,d_cut)
  from cctbx.maptbx.segment_and_split_map import score_map

  target_in_all_regions,regions,sa_ratio,score,skew,kurtosis=score_map(
    map_data=map_data,
    solvent_fraction=solvent_fraction,
    fraction_occupied=fraction_occupied,
    wrapping=use_sg_symmetry,
    sa_percent=sa_percent,
    region_weight=region_weight,
    out=sys.stdout)
  print "SCORING  %.1f %.1f %.3f  %.3f  %.3f   %.3f" %(
    target_in_all_regions,regions,sa_ratio,score,skew,kurtosis)
  return score


def get_kurtosis(data=None):
  mean=data.min_max_mean().mean
  sd=data.standard_deviation_of_the_sample()
  x=data-mean
  return (x**4).min_max_mean().mean/sd**4


class refinery:
  def __init__(self,ma,phases,b,d_cut,
    residual_type=None,
    solvent_fraction=None,
    region_weight=None,
    sa_percent=None,
    fraction_occupied=None,
    use_sg_symmetry=None,
    eps=0.01,
    tol=0.01,
    max_iterations=20,
    dummy_run=False):

    self.ma=ma
    self.phases=phases
    self.d_cut=d_cut

    self.tol=tol
    self.eps=eps
    self.max_iterations=max_iterations

    self.solvent_fraction=solvent_fraction
    self.region_weight=region_weight
    self.residual_type=residual_type
    self.sa_percent=sa_percent
    self.fraction_occupied=fraction_occupied
    self.use_sg_symmetry=use_sg_symmetry

    self.x = flex.double(b)

  def run(self):

    scitbx.lbfgs.run(target_evaluator=self,
      termination_params=scitbx.lbfgs.termination_parameters(
        traditional_convergence_test_eps=self.tol,
                     max_iterations=self.max_iterations,
       ))

  def show_result(self):

    b=self.get_b()
    value = -1.*self.residual(b)
    print "Result: b1 %7.2f b2 %7.2f b3 %7.2f d_cut %7.2f %s: %7.3f" %(
     b[0],b[1],b[2],self.d_cut,self.residual_type,value)

    self.sharpened_ma=adjust_amplitudes_linear(
         self.ma,b[0],b[1],b[2],d_cut=self.d_cut)
    return value

  def compute_functional_and_gradients(self):
    b = self.get_b()
    f = self.residual(b)
    g = self.gradients(b)
    return f, g

  def residual(self,b,restraint_weight=100.):

    if self.residual_type=='kurtosis':
      resid=-1.*calculate_kurtosis(self.ma,self.phases,b,self.d_cut)

    elif self.residual_type=='adjusted_sa':
      resid=-1.*calculate_adjusted_sa(self.ma,self.phases,b,
        d_cut=self.d_cut,
        solvent_fraction=self.solvent_fraction,
        region_weight=self.region_weight,
        sa_percent=self.sa_percent,
        fraction_occupied=self.fraction_occupied,
        use_sg_symmetry=self.use_sg_symmetry,)
    else:
      raise Sorry("residual_type must be kurtosis or adjusted_sa")

    # put in restraint so b[1] is not bigger than b[0]
    if b[1]>b[0]:  resid+=(b[1]-b[0])*restraint_weight
    # put in restraint so b[2] <=0
    if b[2]>0:  resid+=b[2]*restraint_weight
    return resid

  def gradients(self,b):

    result = flex.double()
    for i in xrange(len(list(b))):
      rs = []
      for signed_eps in [self.eps, -self.eps]:
        params_eps = deepcopy(b)
        params_eps[i] += signed_eps
        rs.append(self.residual(params_eps))
      result.append((rs[0]-rs[1])/(2*self.eps))
    return result

  def get_b(self):
    return list(self.x)

  def callback_after_step(self, minimizer):
    pass # can do anything here

def calculate_kurtosis(ma,phases,b,d_cut):
  map_data=get_sharpened_map(ma,phases,b,d_cut)
  return get_kurtosis(map_data.as_1d())

def run(map_coeffs=None,
  d_cut=2.9,
  residual_type='kurtosis',
  solvent_fraction=0.99,
  region_weight=20.,
  sa_percent=30.,
  fraction_occupied=0.20,
  n_bins=20,
  eps=0.01,
  use_sg_symmetry=False,
  out=sys.stdout):

  (d_max,d_min)=map_coeffs.d_max_min()
  phases=map_coeffs.phases(deg=True)
  ma=map_coeffs.as_amplitude_array()

  # Get initial value

  b=[0,0,0]
  improved=False
  print >>out,"Getting starting value ..."
  refined = refinery(ma,phases,b,d_cut,
    residual_type=residual_type,
    solvent_fraction=solvent_fraction,
    region_weight=region_weight,
    sa_percent=sa_percent,
    fraction_occupied=fraction_occupied,
    use_sg_symmetry=use_sg_symmetry,
    eps=eps)


  starting_result=refined.show_result()
  print >>out,"Starting value: %7.2f" %(starting_result)
  best_sharpened_ma=ma
  best_result=starting_result


  print >>out,"Normalizing structure factors..."
  mean_f,bin_d_min=get_means(d_min,d_max,ma,n_bins)
  ma=quasi_normalize_structure_factors(ma,set_to_minimum=0.01)

  refined = refinery(ma,phases,b,d_cut,
    residual_type=residual_type,
    solvent_fraction=solvent_fraction,
    region_weight=region_weight,
    sa_percent=sa_percent,
    fraction_occupied=fraction_occupied,
    use_sg_symmetry=use_sg_symmetry,
    eps=eps)

  starting_normalized_result=refined.show_result()
  print >>out,"Starting value after normalization: %7.2f" %(
     starting_normalized_result)

  if starting_normalized_result>best_result:
    improved=True
    best_sharpened_ma=ma
    best_result=starting_normalized_result

  refined.run()

  final_result=refined.show_result()
  print >>out,"Final value: %7.2f" %(
     final_result)

  if final_result>best_result:
    best_sharpened_ma=refined.sharpened_ma
    best_result=final_result
    improved=True
  print >>out,"Best overall result: %7.2f: " %(best_result)

  if improved:
    # return updated map coefficients
    return best_sharpened_ma.phase_transfer(phase_source=phases,deg=True)


if (__name__ == "__main__"):
  args=sys.argv[1:]
  eps=0.01
  residual_type='kurtosis'
  if 'adjusted_sa' in args:
    residual_type='adjusted_sa'
    eps=0.5
  d_cut=2.9 # need to set this as nominal resolution
  # get data
  map_coeffs=get_amplitudes(args)

  new_map_coeffs=run(map_coeffs=map_coeffs,
    d_cut=d_cut,
    eps=eps,residual_type=residual_type)
  mtz_dataset=new_map_coeffs.as_mtz_dataset(column_root_label="FWT")
  mtz_dataset.mtz_object().write(file_name='sharpened.mtz')
