from __future__ import division
import time
import sys, os

class Keep: pass

class UserError(Exception):

  # trick to get just "UserError" instead of "libtbx.utils.UserError"
  __module__ = "exceptions"

  def __init__(self, *args, **keyword_args):
    self.previous_tracebacklimit = getattr(sys, "tracebacklimit", None)
    sys.tracebacklimit = 0
    Exception.__init__(self, *args, **keyword_args)

  def __str__(self):
    self.reset_tracebacklimit()
    return Exception.__str__(self)

  def __del__(self):
    self.reset_tracebacklimit()

  def reset_tracebacklimit(self):
    if (hasattr(sys, "tracebacklimit")):
      if (self.previous_tracebacklimit is None):
        del sys.tracebacklimit
      else:
        sys.tracebacklimit = self.previous_tracebacklimit

def format_exception():
  type_, value = sys.exc_info()[:2]
  type_ = str(type_)
  if (type_.startswith("exceptions.")): type_ = type_[11:]
  return "%s: %s" % (type_, str(value))

def date_and_time():
  localtime = time.localtime()
  if (time.daylight and localtime[8] != 0):
    tzname = time.tzname[1]
    offs = -time.altzone
  else:
    tzname = time.tzname[0]
    offs = -time.timezone
  return time.strftime("Date %Y-%m-%d Time %H:%M:%S", localtime) \
       + " %s %+03d%02d" % (tzname, offs//3600, offs//60%60)

def format_cpu_times(show_micro_seconds_per_tick=True):
  t = os.times()
  result = "u+s,u,s: %.2f %.2f %.2f" % (t[0] + t[1], t[0], t[1])
  if (show_micro_seconds_per_tick):
    try: python_ticker = sys.gettickeraccumulation()
    except AttributeError: pass
    else:
      result += " micro-seconds/tick: %.3f" % ((t[0]+t[1])/python_ticker*1.e6)
  return result

def exercise():
  try:
    raise RuntimeError("Trial")
  except:
    assert format_exception() == "RuntimeError: Trial"
  print "OK"

if (__name__ == "__main__"):
  exercise()
