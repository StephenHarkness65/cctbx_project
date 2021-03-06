from __future__ import division
import os
import libtbx.auto_build.bootstrap

def run():
  root = os.environ.get('LIBTBX_BUILD')
  if root:
    root = os.path.join(root, '..')
    os.chdir(root)
  libtbx.auto_build.bootstrap.run()

if (__name__ == "__main__"):
  run()
