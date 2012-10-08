# BEGIN_COPYRIGHT
# 
# Copyright 2012 CRS4.
# 
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
# 
# END_COPYRIGHT

"""
Important environment variables
-------------------------------

The Pydoop setup looks in a number of default paths for what it
needs.  If necessary, you can override its behaviour or provide an
alternative path by exporting the environment variables below::

  JAVA_HOME, e.g., /opt/sun-jdk
  HADOOP_HOME, e.g., /opt/hadoop-1.0.2

Other relevant environment variables include::

  BOOST_PYTHON: name of the Boost.Python library, with the leading 'lib'
    and the trailing extension stripped. Defaults to 'boost_python'.
  HADOOP_VERSION, e.g., 0.20.2-cdh3u4 (override Hadoop's version string).
"""

import os, platform, re, glob, shutil
from distutils.core import setup
from distutils.extension import Extension
from distutils.command.build_ext import build_ext as distutils_build_ext
from distutils.command.clean import clean as distutils_clean
from distutils.command.build import build as distutils_build
from distutils.command.build_py import build_py as distutils_build_py
from distutils.errors import DistutilsSetupError
from distutils import log

import pydoop


try:
  JAVA_HOME = os.environ["JAVA_HOME"]
except KeyError:
  raise RuntimeError("java home not found, try setting JAVA_HOME")
HADOOP_HOME = pydoop.hadoop_home(fallback=None)
HADOOP_VERSION_INFO = pydoop.hadoop_version_info()
BOOST_PYTHON = os.getenv("BOOST_PYTHON", "boost_python")
PIPES_SRC = ["src/%s.cpp" % _ for _ in (
  "pipes",
  "pipes_context",
  "pipes_test_support",
  "pipes_serial_utils",
  "exceptions",
  "pipes_input_split",
  )]
HDFS_SRC = ["src/%s.cpp" % _ for _ in (
  "hdfs_fs",
  "hdfs_file",
  "hdfs_common",
  )]
PIPES_EXT_NAME = "_pipes"
HDFS_EXT_NAME = "_hdfs"


# ---------
# UTILITIES
# ---------

def get_arch():
  bits, _ = platform.architecture()
  if bits == "64bit":
    return "amd64", "64"
  return "i386", "32"

HADOOP_ARCH_STR = "Linux-%s-%s" % get_arch()


def get_java_include_dirs(java_home):
  p = platform.system().lower()  # Linux-specific
  java_inc = os.path.join(java_home, "include")
  java_platform_inc = "%s/%s" % (java_inc, p)
  return [java_inc, java_platform_inc]


def get_java_library_dirs(java_home):
  a = get_arch()[0]
  return [os.path.join(java_home, "jre/lib/%s/server" % a)]


def mtime(fn):
  return os.stat(fn).st_mtime


def must_generate(target, prerequisites):
  try:
    return max(mtime(p) for p in prerequisites) > mtime(target)
  except OSError:
    return True


def get_version_string(filename="VERSION"):
  try:
    with open(filename) as f:
      return f.read().strip()
  except IOError:
    raise DistutilsSetupError("failed to read version info")


def write_config(filename="pydoop/config.py"):
  prereq = "DEFAULT_HADOOP_HOME"
  if not os.path.exists(prereq):
    with open(prereq, "w") as f:
      f.write("%s\n" % HADOOP_HOME)
  if must_generate(filename, [prereq]):
    with open(filename, "w") as f:
      f.write("# GENERATED BY setup.py\n")
      f.write("DEFAULT_HADOOP_HOME='%s'\n" % HADOOP_HOME)


def write_version(filename="pydoop/version.py"):
  prereq = "VERSION"
  if must_generate(filename, [prereq]):
    version = get_version_string(filename=prereq)
    with open(filename, "w") as f:
      f.write("# GENERATED BY setup.py\n")
      f.write("version='%s'\n" % version)


def get_hdfs_macros(hdfs_hdr):
  """
  Search libhdfs headers for specific features.
  """
  hdfs_macros = []
  with open(hdfs_hdr) as f:
    t = f.read()
  delete_args = re.search(r"hdfsDelete\((.+)\)", t).groups()[0].split(",")
  cas_args = re.search(r"hdfsConnectAsUser\((.+)\)", t).groups()[0].split(",")
  if len(delete_args) > 2:
    hdfs_macros.append(("RECURSIVE_DELETE", None))
  if len(cas_args) > 3:
    hdfs_macros.append(("CONNECT_GROUP_INFO", None))
  return hdfs_macros


def patch_hadoop_src():
  hadoop_tag = "hadoop-%s" % HADOOP_VERSION_INFO
  patch_fn = "patches/%s.patch" % hadoop_tag
  src_dir = "src/%s" % hadoop_tag
  patched_src_dir = "%s.patched" % src_dir
  if must_generate(patched_src_dir, [src_dir, patch_fn]):
    shutil.rmtree(patched_src_dir, ignore_errors=True)
    shutil.copytree(src_dir, patched_src_dir)
    os.utime(patched_src_dir, None)
    cmd = "patch -d %s -N -p1 < %s" % (patched_src_dir, patch_fn)
    if os.system(cmd):
      raise DistutilsSetupError("Error applying patch.  Command: %s" % cmd)
  return patched_src_dir


# ------------------------------------------------------------------------------
# Create extension objects.
#
# We first create some basic Extension objects to pass to the distutils setup
# function.  They act as little more than placeholders, simply telling distutils
# the name of the extension and what source files it depends on.
#   functions:  create_basic_(pipes|hdfs)_ext
#
# When our build_pydoop_ext command is invoked, we build a complete extension
# object that includes all the information required for the build process.  In
# particular, it includes all the relevant paths.
#
# The reason for the two-stage process is to delay verifying paths to when
# they're needed (build) and avoiding those checks for other commands (such
# as clean).
# ------------------------------------------------------------------------------

def create_basic_pipes_ext():
  return BoostExtension(PIPES_EXT_NAME, PIPES_SRC, [])


def create_basic_hdfs_ext():
  return BoostExtension(HDFS_EXT_NAME, HDFS_SRC, [])


def create_full_pipes_ext(patched_src_dir):
  include_dirs = ["%s/%s/api" % (patched_src_dir, _) for _ in "pipes", "utils"]
  libraries = ["pthread", BOOST_PYTHON]
  if HADOOP_VERSION_INFO.tuple() != (0, 20, 2):
    libraries.append("ssl")
  return BoostExtension(
    pydoop.complete_mod_name(PIPES_EXT_NAME, HADOOP_VERSION_INFO),
    PIPES_SRC,
    glob.glob("%s/*/impl/*.cc" % patched_src_dir),
    include_dirs=include_dirs,
    libraries=libraries
    )


def create_full_hdfs_ext(patched_src_dir):
  java_include_dirs = get_java_include_dirs(JAVA_HOME)
  log.info("java_include_dirs: %r" % (java_include_dirs,))
  include_dirs = java_include_dirs + ["%s/libhdfs" % patched_src_dir]
  java_library_dirs = get_java_library_dirs(JAVA_HOME)
  log.info("java_library_dirs: %r" % (java_library_dirs,))
  return BoostExtension(
    pydoop.complete_mod_name(HDFS_EXT_NAME, HADOOP_VERSION_INFO),
    HDFS_SRC,
    glob.glob("%s/libhdfs/*.c" % patched_src_dir),
    include_dirs=include_dirs,
    library_dirs=java_library_dirs,
    runtime_library_dirs=java_library_dirs,
    libraries=["pthread", BOOST_PYTHON, "jvm"],
    define_macros=get_hdfs_macros(
      os.path.join(patched_src_dir, "libhdfs", "hdfs.h")
      ),
    )


# ---------------------------------------
# Custom distutils extension and commands
# ---------------------------------------

class BoostExtension(Extension):
  """
  Customized Extension class that generates the necessary Boost.Python
  export code.
  """
  export_pattern = re.compile(r"void\s+export_(\w+)")

  def __init__(self, name, wrap_sources, aux_sources, **kw):
    Extension.__init__(self, name, wrap_sources+aux_sources, **kw)
    self.module_name = self.name.rsplit(".", 1)[-1]
    self.wrap_sources = wrap_sources

  def generate_main(self):
    destdir = os.path.split(self.wrap_sources[0])[0]  # should be ok
    outfn = os.path.join(destdir, "%s_main.cpp" % self.module_name)
    if must_generate(outfn, self.wrap_sources):
      log.debug("generating main for %s\n" % self.name)
      first_half = ["#include <boost/python.hpp>"]
      second_half = ["BOOST_PYTHON_MODULE(%s){" % self.module_name]
      for fn in self.wrap_sources:
        with open(fn) as f:
          code = f.read()
        m = self.export_pattern.search(code)
        if m is not None:
          fun_name = "export_%s" % m.groups()[0]
          first_half.append("void %s();" % fun_name)
          second_half.append("%s();" % fun_name)
      second_half.append("}")
      with open(outfn, "w") as outf:
        for line in first_half:
          outf.write("%s%s" % (line, os.linesep))
        for line in second_half:
          outf.write("%s%s" % (line, os.linesep))
    return outfn


class build_pydoop_ext(distutils_build_ext):

  def finalize_options(self):
    distutils_build_ext.finalize_options(self)
    patched_src_dir = patch_hadoop_src()
    self.extensions = [
      create_full_pipes_ext(patched_src_dir),
      create_full_hdfs_ext(patched_src_dir),
      ]
    for e in self.extensions:
      e.sources.append(e.generate_main())

  def build_extension(self, ext):
    try:
      self.compiler.compiler_so.remove("-Wstrict-prototypes")
    except ValueError:
      pass
    distutils_build_ext.build_extension(self, ext)


def create_ext_modules():
  ext_modules = []
  ext_modules.append(create_basic_pipes_ext())
  ext_modules.append(create_basic_hdfs_ext())
  return ext_modules


class pydoop_clean(distutils_clean):
  """
  Custom clean action that removes files generated by the build process.
  """
  def run(self):
    distutils_clean.run(self)
    this_dir = os.path.dirname(os.path.realpath(__file__))
    shutil.rmtree(os.path.join(this_dir, 'dist'), ignore_errors=True)
    pydoop_src_path = os.path.join(this_dir, 'src')
    r = re.compile('(%s|%s)_.*_main.cpp$' % (HDFS_EXT_NAME, PIPES_EXT_NAME))
    paths = filter(r.search, os.listdir(pydoop_src_path))
    absolute_paths = [os.path.join(pydoop_src_path, f) for f in paths]
    for f in absolute_paths:
      if not self.dry_run:
        try:
          if os.path.exists(f):
            os.remove(f)
        except OSError as e:
          log.warn("Error removing file: %s" % e)


class pydoop_build(distutils_build):

  def run(self):
    log.info("hadoop_home: %r" % (HADOOP_HOME,))
    log.info("hadoop_version: %r" % (HADOOP_VERSION_INFO.tuple(),))
    log.info("java_home: %r" % (JAVA_HOME,))
    distutils_build.run(self)
    self.__build_java_component()

  def __build_java_component(self):
    compile_cmd = "javac"
    classpath = ':'.join(
        glob.glob(os.path.join(HADOOP_HOME, 'hadoop-*.jar')) +
        glob.glob(os.path.join(HADOOP_HOME, 'lib', '*.jar'))
      )
    if classpath:
      compile_cmd += " -classpath %s" % classpath
    else:
      log.warn("could not set classpath, java code may not compile")
    class_dir = os.path.join(self.build_temp, 'pydoop_java')
    package_path = os.path.join(self.build_lib, 'pydoop', pydoop.__jar_name__)
    if not os.path.exists(class_dir):
      os.mkdir(class_dir)
    compile_cmd += " -d '%s'" % class_dir
    java_files = ["src/it/crs4/pydoop/NoSeparatorTextOutputFormat.java"]
    if HADOOP_VERSION_INFO >= (1, 0, 0):
      java_files.append("src/it/crs4/pydoop/pipes/*")
    log.info("Compiling Java classes")
    for f in java_files:
      compile_cmd += " %s" % f
      log.debug("Command: %s", compile_cmd)
      ret = os.system(compile_cmd)
      if ret:
        raise DistutilsSetupError(
          "Error compiling java component.  Command: %s" % compile_cmd
          )
    package_cmd = "jar -cf %(package_path)s -C %(class_dir)s ./it" % {
      'package_path': package_path, 'class_dir': class_dir
      }
    log.info("Packaging Java classes")
    log.debug("Command: %s", package_cmd)
    ret = os.system(package_cmd)
    if ret:
      raise DistutilsSetupError(
        "Error packaging java component.  Command: %s" % package_cmd
        )


class pydoop_build_py(distutils_build_py):

  def run(self):
    write_config()
    write_version()
    distutils_build_py.run(self)


setup(
  name="pydoop",
  version=get_version_string(),
  description=pydoop.__doc__.strip().splitlines()[0],
  long_description=pydoop.__doc__.lstrip(),
  author=pydoop.__author__,
  author_email=pydoop.__author_email__,
  url=pydoop.__url__,
  download_url="https://sourceforge.net/projects/pydoop/files/",
  packages=[
    "pydoop",
    "pydoop.hdfs",
    "pydoop.app",
    ],
  cmdclass={
    "build": pydoop_build,
    "build_py": pydoop_build_py,
    "build_ext": build_pydoop_ext,
    "clean": pydoop_clean
    },
  ext_modules=create_ext_modules(),
  scripts=["scripts/pydoop"],
  platforms=["Linux"],
  license="Apache-2.0",
  keywords=["hadoop", "mapreduce"],
  classifiers=[
    "Programming Language :: Python",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: POSIX :: Linux",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Intended Audience :: Developers",
    ],
  )

# vim: set sw=2 ts=2 et
