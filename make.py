#!/usr/bin/env python

import getopt
import os
import subprocess
import sys

_USAGE = """
make.py [options]

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
    def __init__(self, graphene, outdir, verbose=False):
        self.graphene = graphene
        self.outdir = outdir
        self.verbose = verbose

    def make_manifest(self, premanifest):
        args = []
        args.append('--graphene %s' % self.graphene)
        args.append('--output %s/manifest' % self.outdir)
        if self.verbose:
            args.append('--verbose')
        args.append(premanifest)
        cmd  = './makemanifest.py %s' % ' '.join(args)
        _run_cmd(cmd)

    def sign_manifest(self, keyfile):
        manifest = os.path.join(self.outdir, 'manifest')
        manifest_sgx = os.path.join(self.outdir, 'manifest.sgx')
        libpal = os.path.join(self.graphene, 'Runtime', 'libpal-Linux-SGX.so')

        args = []
        args.append('-output %s' % manifest_sgx)
        args.append('-key %s' % keyfile)
        args.append('-libpal %s' % libpal)
        args.append('-manifest %s' % manifest)
        cmd = './pal-sgx-sign %s' % ' '.join(args)
        _run_cmd(cmd)
        os.chmod(manifest_sgx, 0775) 

    def get_token(self):
        args = []
        args.append('-output %s/token' % self.outdir)
        args.append('-sig %s/manifest.sgx.sig' % self.outdir)
        cmd = './pal-sgx-get-token %s' % ' '.join(args)
        _run_cmd(cmd)

def main(argv):
    shortopts = 'g:hk:m:o:p:v'
    longopts = ['graphene=', 'help', 'key=', 'manifest=', 'outdir=',
            'pre-manifest=','verbose']
    # options
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
        elif o in ('-p', '--premanifest'):
            premanifest = a
        elif o in ('-v', '--verbose'):
            verbose = True
        else:
            assert False, "unhandled option '%s'" % o

    maker = Maker(graphene, outdir, verbose)
    maker.make_manifest(premanifest)
    maker.sign_manifest(keyfile)
    maker.get_token()

if __name__ == '__main__':
    main(sys.argv)
