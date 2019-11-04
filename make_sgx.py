#!/usr/bin/env python

import getopt
import os
import subprocess
import sys

_USAGE = """
make_sgx.py [options]

Make a manifest.sgx file.

In the usual case, a pre-manifest file is specified.  make_sgx.py
then converts this pre-maniest to a Graphene manifest file,
invokes pal-sgx-sign to sign the enclave image, and finall invokeds
pal-sgx-get-token to retrieve a launch token.

  options:
    -g, --graphene GRAPHENE_PATH
        Mandatory.
        The path to the graphene root directory

    -h, --help
        Display this message and exit.

    -k, --key SIGNING_KEY
        Mandatory.
        The private key for signing an enclave image.

    -m, --manifest GRAPHENE_MANIFST
        A graphene .manifest file

    -o, --outdir PATH
        The output directory in which to place the manifest.sgx file
        and launch token.

        If not given, these assets are placed in the current working
        directory.

    -p, --pre-manifest PRE_MANIFEST
        A simplified version of a graphene manifest -- what I call
        a pre-manifest

    -t, --tool-dir PATH
        The directory that has the tools:
            - make_manifest.py
            - pal-sgx-sign
            - pal-sgx-get-token
        
        If not given, the tools are assumed to be on the user's $PATH.

    -v, --verbose
        Enable verbose logging.
""".strip()

verbose = False

def _usage(exitcode):
    sys.stderr.write('%s\n' % _USAGE)
    sys.exit(exitcode)

def _log(tag, fmt, *args):
    fmt = '[%s] %s' % (tag, fmt)
    if not fmt.endswith('\n'):
        fmt += '\n'
    sys.stderr.write(fmt % args)

def _debug(fmt, *args):
    if not verbose:
        return
    _log('debug', fmt, *args)

def _warn(fmt, *args):
    _log('warn', fmt, *args)

def _die(fmt, *args):
    _log('die', fmt, *args)
    sys.exit(1)

def _run_cmd(cmd):
    _debug('running cmd: %s', cmd)
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as err:
        _die("cmd '%s' returned %d: %s", cmd, err.returncode, str(err)) 

class Maker:
    def __init__(self, graphene, outdir, tooldir=None, verbose=False):
        self.graphene = graphene
        self.outdir = outdir
        self.tooldir = tooldir
        self.verbose = verbose

    def _executable_path(self, name):
        if self.tooldir:
            return os.path.join(self.tooldir, name)
        else:
            return name

    def _out_path(self, name):
        if self.outdir:
            return os.path.join(self.outdir, name)
        else:
            return name

    def make_manifest(self, premanifest):
        args = []
        args.append('--graphene %s' % self.graphene)
        args.append('--output %s' % self._out_path('manifest'))
        if self.verbose:
            args.append('--verbose')
        args.append(premanifest)
        executable = self._executable_path('make_manifest.py')
        cmd = '%s %s' % (executable, ' '.join(args))
        _run_cmd(cmd)

    def sign_manifest(self, keyfile):
        manifest = self._out_path('manifest')
        manifest_sgx = self._out_path('manifest.sgx')
        libpal = os.path.join(self.graphene, 'Runtime', 'libpal-Linux-SGX.so')

        args = []
        args.append('-output %s' % manifest_sgx)
        args.append('-key %s' % keyfile)
        args.append('-libpal %s' % libpal)
        args.append('-manifest %s' % manifest)
        executable = self._executable_path('pal-sgx-sign')
        cmd = '%s %s' % (executable, ' '.join(args))
        _run_cmd(cmd)
        os.chmod(manifest_sgx, 0775) 

    def get_token(self):
        args = []
        args.append('-output %s' % self._out_path('manifest.sgx.token'))
        args.append('-sig %s' % self._out_path('manifest.sgx.sig'))
        executable = self._executable_path('pal-sgx-get-token')
        cmd = '%s %s' % (executable, ' '.join(args))
        _run_cmd(cmd)

    def finalize(self):
        # XXX: Hack (the loader expects the manifest.sgx file to
        # have a name like foo.manifest.sgx
        if self.outdir:
            new_name = self._out_path('%s.manifest.sgx' %
                    os.path.basename(self.outdir))
            os.rename(self._out_path('manifest.sgx'), new_name)

def main(argv):
    shortopts = 'g:hk:m:o:p:t:v'
    longopts = ['graphene=', 'help', 'key=', 'manifest=', 'outdir=',
            'pre-manifest=','tool-dir=', 'verbose']
    # options
    graphene = None
    keyfile = None
    manifest = None
    outdir = None
    premanifest = None
    tooldir = None
    global verbose

    try:
        opts, args = getopt.getopt(argv[1:], shortopts, longopts)
    except getopt.GetoptError as err:
        sys.stderr.write('%s\n', str(errr))
        _usage(1)

    for o, a in opts:
        if o in ('-g', '--graphene'):
            graphene = a
        elif o in ('-h', '--help'):
            _usage(0)
        elif o in ('-k', '--key'):
            keyfile = a
        elif o in ('-m', '--manifest'):
            manifest = a
        elif o in ('-o', '--outdir'):
            outdir = a
        elif o in ('-p', '--pre-manifest'):
            premanifest = a
        elif o in ('-t', '--tool-dir'):
            tooldir = a
        elif o in ('-v', '--verbose'):
            verbose = True
        else:
            assert False, "unhandled option '%s'" % o

    if not graphene:
        sys.stderr.write('error: --graphene must be specified\n')
        _usage(1)

    if not keyfile:
        sys.stderr.write('error: --key must be specified\n')
        _usage(1)

    maker = Maker(graphene, outdir, tooldir, verbose)
    maker.make_manifest(premanifest)
    maker.sign_manifest(keyfile)
    maker.get_token()
    maker.finalize()
    
if __name__ == '__main__':
    main(sys.argv)
