#!/usr/bin/env python

import binascii
import collections
import errno
import getopt
import os
import re
import subprocess
import sys
import urlparse

_USAGE = """
makemanifest.py [options] CONF

  Convert a configuration to a Graphene manifest.

  options
    -g, --graphene GRAPHENE_ROOT
        Path to the Graphene root directory.

    -h, --help
        Show this help message and exit.

    -o, --output OUTPUT
        The output manifest file

    -v, --verbose
        Verbose logging

  args
    CONF
        The configuration file.  CONF is a simplified form of the
        graphene manifest.  CONF supports the following directives
""".strip()

_CONFIG_MAX = 4096

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

def _mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

# nargs = mimimum number of args needed; varargs is a boolean that is
# true if additional args to the directive may be present.
Directive = collections.namedtuple('Directive', ['fn', 'nargs', 'varargs'])

class ManifestMaker:
    def __init__(self, graphene, inpath, out_manifest):
        self.graphene = os.path.abspath(graphene)
        self.inpath = inpath
        self.out_manifest = os.path.abspath(out_manifest)
        self.linenum = 0

        self._directive_table = {
            'MOUNT':  Directive(self._mount_fn, 3, True),
            'DEBUG':  Directive(self._debug_fn, 1, False),
            'EXEC':   Directive(self._exec_fn, 1, False),
            'MODULE': Directive(self._module_fn, 1, False),
            'BIND':   Directive(self._bind_fn, 2, False),
            'ENCLAVE_SIZE': Directive(self._enclave_size_fn, 1, False),
            'THREADS': Directive(self._threads_fn, 1, True),
            'TIMESERVER': Directive(self._timeserver_fn, 3, False),
            'CAFILE': Directive(self._cafile_fn, 1, False),
        }

        self._uri_schemes = ('file', 'pipe', 'tcp', 'udp')
        self._fstypes = ('chroot', 'nextfs', 'mdish', 'tnt')
        self._glibc_libs = (
            'ld-linux-x86-64.so.2',
            'libc.so',
            'libc.so.6',
            'libdl.so.2',
            'libm.so.6',
            'libnss_dns.so.2',
            'libpthread.so.0',
            'libresolv.so.2',
            'librt.so.1',
            'libthread_db.so.1',
            'libutil.so.1'
            )

        self.libpaths = collections.OrderedDict()
        self.trusted_libs = collections.OrderedDict()
        self.ro_uris = []
        self.rw_uris = []
        self.out = []

    #------------------------------------------------------
    # error checking / reporting
    #------------------------------------------------------

    def _parse_err(self, fmt, *args):
        ffmt = '%s:%d %s' % (self.inpath, self.linenum, fmt)
        if not ffmt.endswith('\n'):
            ffmt += '\n'
        sys.stderr.write(ffmt % args)
        sys.exit(1)

    def _check_uri(self, uri):
        pos = uri.find(':')
        if pos== -1:
            self._parse_err('invalid uri \"%s\"', uri)
        scheme = uri[:pos]
        if scheme not in self._uri_schemes:
            self._parse_err('unrecognized uri scheme \"%s\" (uri=\"%s\")',
                    scheme, uri)

    def _check_uri_type(self, uri, expected_type):
        pos = uri.find(':')
        if pos== -1:
            self._parse_err('invalid uri "%s"', uri)
        scheme = uri[:pos]
        if scheme != expected_type:
            self._parse_err('invalid uri "%s": expected type "%s"', uri, expected_type)

    def _check_fstype(self, fstype):
        if fstype not in self._fstypes:
            self._parse_error('unrecognized fstype \"%s\"', fstype)

    def _check_int(self, s):
        try:
            v = int(s)
        except ValueError:
            self._parse_error('expected an integer value but got \"%s\"', s)
        else:
            return v

    def _check_float(self, s):
        try:
            v = float(s)
        except ValueError:
            self._parse_error('expected a float value but got \"%s\"', s)
        else:
            return v

    def _check_timeserver_url(self, url):
        p = urlparse.urlparse(url)
        if p.scheme != 'udp':
            self._parse_error('invalid timeserver url: scheme must be "udp"')
        if p.path or p.params or p.query or p.fragment:
            self._parse_error('invalid timeserver url: found path/params/query/fragment')
        if p.port:
            if p.netloc != '%s:%d' % (p.hostname, p.port):
                self._parse_error('invalid timeserver url: bad netloc')
        # TODO test p.hostname matches regex for ipv4 address

    #------------------------------------------------------
    # path manipulation
    #------------------------------------------------------

    def _graphene_path(self, subpath):
        return os.path.join(self.graphene, subpath)

    def _uri_path(self, uri):
        self._check_uri_type(uri, 'file')
        return uri[5:]

    def _uri_to_abs_uri(self, uri):
        path = self._uri_path(uri)
        return 'file:%s' % os.path.abspath(path)

    #------------------------------------------------------
    # misc helpers
    #------------------------------------------------------

    def _out(self, manifest_directive):
        self.out.append(manifest_directive)

    def _run_cmd(self, cmd):
        _debug('running cmd: %s', cmd)
        try:
            output = subprocess.check_output(cmd, shell=True)
        except subprocess.CalledProcessError as err:
            _die("cmd '%s' returned %d: %s", cmd, err.returncode, str(err))
        else:
            return output

    def _lstrip_00_bytes(self, a):
        h = a[0]
        while h == '00':
            a.pop(0)
            h = a[0]

    def _dump_pem_pubkey(self, pubfile):
        cmd = 'openssl rsa -inform PEM -pubin -in %s -text -noout' % pubfile
        self._run_cmd(cmd)
        output = subprocess.check_output(cmd, shell=True)
        lines = output.splitlines()

        bits = 0
        mod_hex = []
        exp_hex = []

        # XXX: really gross parsing of the openssl output
        for i, line in enumerate(lines):
            if re.match(r'\s+[\da-f]{2}:', line):
                line = line.strip().rstrip(':')
                mod_hex.extend(line.split(':'))
            else: 
                mobj = re.match(r'Exponent: \d+ \(0x([\da-f]+)\)', line)
                if mobj:
                    hs = mobj.group(1)
                    if len(hs) % 2:
                        hs = '0' + hs
                    for i in xrange(0, len(hs), 2):
                        exp_hex.append(hs[i:i+2])
                    continue
                mobj = re.match(r'Public-Key: \((\d+) bit\)', line)
                if mobj:
                    bits = int(mobj.group(1))

        self._lstrip_00_bytes(mod_hex)
        self._lstrip_00_bytes(exp_hex)

        # TODO: error checking
        return (mod_hex, exp_hex)

    def _cert_pem_to_der_buf(self, cert_pemfile):
        cmd = 'openssl x509 -outform der -in %s' % cert_pemfile
        output = self._run_cmd(cmd)
        return output


    def _add_trusted_depends(self, host_uri):
        path = self._uri_path(host_uri)
        cmd = 'ldd %s' % path
        output = self._run_cmd(cmd)
        for mobj in re.finditer(r'^\s*(.+) => (.+) \(0x[a-f0-9]+\)\s*$', 
                output, re.MULTILINE):
            self.trusted_libs[mobj.group(1)] = mobj.group(2)

    def _update_libpaths(self, host_uri, graphene_mntpoint):
        if self.libpaths.has_key(host_uri):
            return
        else:
            _debug('adding new libpath \"%s\" on \"%s\"', host_uri, graphene_mntpoint)
            self.libpaths[host_uri] = graphene_mntpoint

    def _make_name(self, name):
        """
        The tags in a graphene key (e.g., tag1.tag2.tag3) can only consist of
        [a-zA-Z0-9_].  Thus, we change any invalid chars in name to _
        """
        return re.sub(r'[^A-Za-z0-9_]', '_', name)

    #------------------------------------------------------
    # directive handlers
    #------------------------------------------------------

    def _mount_fn(self, host_uri, graphene_path, fstype, *options):
        self._check_uri(host_uri)
        self._check_fstype(fstype)
        name = self._make_name(graphene_path)
        self._out('fs.mount.%s.type = %s' % (name, fstype))
        self._out('fs.mount.%s.path = %s' % (name, graphene_path))
        self._out('fs.mount.%s.uri = %s' % (name, host_uri))

        # special case for ro/rw option for chroot
        # no additional work for ro; for rw, must add mount to list
        # of allowed files.
        if fstype == 'chroot': 
            if len(options) != 1:
                self._parse_err('chroot mount: missing ro/rw option')
            opt = options[0]
            if opt not in ('ro', 'rw'):
                self._parse_err('chroot mount: invalid option \"%s\"', opt)
            if opt == 'ro':
                self.ro_uris.append(host_uri)
            else:
                self.rw_uris.append(host_uri)

    def _debug_fn(self, onoff):
        if onoff == 'on':
            self._out('loader.debug_type = inline')
        elif onoff == 'off':
            self._out('loader.debug_type = none')
        else:
            self._out('DEBUG must be "on" or "off", not "%s"' % onoff)

    def _exec_fn(self, host_uri):
        self._check_uri(host_uri)
        basename = os.path.basename(host_uri)
        abs_uri = self._uri_to_abs_uri(host_uri)
        self._out('loader.exec = %s' % abs_uri)
        self._out('loader.execname = %s' % basename)
        self._add_trusted_depends(host_uri)

    def _module_fn(self, host_uri):
        name = os.path.basename(host_uri)
        self.trusted_libs[name] = self._uri_path(host_uri)
        self._add_trusted_depends(host_uri)

    def _bind_fn(self, ip, port):
        self._check_int(port)
        name = self._make_name('%s:%s' % (ip, port))
        self._out('net.allow_bind.%s = %s:%s' % (name, ip, port))

    def _enclave_size_fn(self, mb):
        v = self._check_int(mb)
        self._out('sgx.enclave_size = %dM' % v)

    def _threads_fn(self, num, *options):
        v = self._check_int(num)
        self._out('sgx.thread_num = %d' % v)
        if options:
            if len(options) != 1:
                self._parse_err('THREADS: invalid options "%s"', str(options))
            if options[0] != 'exitless':
                self._parse_err('THREADS: invalid option %s"', options[0])
            self._out('sgx.rpc_thread_num = %d' % v)


    def _timeserver_fn(self, url, pubkey_file, rate):
        #self._check_timeserver_url(url)
        mod_hex, exp_hex = self._dump_pem_pubkey(pubkey_file)
        r = self._check_float(rate)
        if r > 1 or r < 0:
            self._parse_error('TIMESERVER: invalid rate: %f; must be >= 0 and <= 1', r)
        r = int(r * 10000)
        self._out('timeserver.url = %s' % url);
        self._out('timeserver.rsa_n = %s' % ''.join(mod_hex))
        self._out('timeserver.rsa_e = %s' % ''.join(exp_hex))
        self._out('timeserver.rate = %d' % r)
        
    def _cafile_fn(self, cafile_pem):
        der = self._cert_pem_to_der_buf(cafile_pem)
        der_hex = binascii.hexlify(der)
        if len(der_hex) > _CONFIG_MAX:
            self._parse_err('cafile_pem \"%s\": conversion to der hex is too big (%d)',
                    len(der_hex))
        self._out('phoenix.ca_der = %s' % der_hex)

    #------------------------------------------------------
    # Post processing steps
    #------------------------------------------------------
    def _postprocess_trusted_libs(self):
        fmt = 'sgx.trusted_files.%s = %s'
        for name, path in self.trusted_libs.iteritems():
            if name in self._glibc_libs:
                host_uri = 'file:' + self._graphene_path(os.path.join('Runtime', name))
                mnt = '/graphene'
            else:
                host_uri = 'file:' + path
                mnt = os.path.dirname(path)
            self._update_libpaths(os.path.dirname(host_uri), mnt)
            name = self._make_name(name)
            self._out(fmt % (name, host_uri))
        # FIXME: fix so we don't have to have this one-off
        host_uri = 'file:%s' % self._graphene_path(os.path.join('Runtime',
            'ld-linux-x86-64.so.2'))
        self._out(fmt % ('ld', host_uri))

    def _postprocess_ro_uris(self):
        fmt = 'sgx.trusted_files.%s = %s'
        for uri in self.ro_uris:
            root = self._uri_path(uri)
            for dirpath, dirnames, filenames in os.walk(root):
                for fname in filenames:
                    fullpath = os.path.join(dirpath, fname)
                    name = self._make_name(fullpath)
                    uri = 'file:' + fullpath
                    self._out(fmt % (name, uri))

    def _postprocess_rw_uris(self):
        fmt = 'sgx.allowed_files.%s = %s'
        for uri in self.rw_uris:
            path = self._uri_path(uri)
            name = self._make_name(path)
            self._out(fmt % (name, uri))

    def _add_loader_cmds(self):
        self._out('loader.preload = file:%s' %
                self._graphene_path('Runtime/libsysdb.so'))

        print '************ %s' % str(self.libpaths)
        # FIXME: we need /graphene to appear first, especially so that
        # ld-linux-x86_64.so.2 gits picked up from the trusted graphene
        # file, and not some other host mount
        ld_library_paths = []
        runtime = 'file:' + self._graphene_path('Runtime')
        if runtime in self.libpaths:
            print '************ HERE **********'
            self.libpaths.pop(runtime)
            ld_library_paths.append('/graphene')

        ld_library_paths.extend(self.libpaths.values())
        self._out('loader.env.LD_LIBRARY_PATH = %s' % \
                ':'.join(ld_library_paths))

    def _add_lib_mounts(self):
        for host_uri, graphene_mntpoint in self.libpaths.iteritems():
            name = self._make_name(graphene_mntpoint)
            self._out('fs.mount.%s.type = %s' % (name, 'chroot'))
            self._out('fs.mount.%s.path = %s' % (name, graphene_mntpoint))
            self._out('fs.mount.%s.uri = %s' % (name, host_uri))

    def _postprocess(self):
        self._postprocess_trusted_libs()
        self._postprocess_rw_uris()
        self._postprocess_ro_uris()
        self._add_lib_mounts()
        self._add_loader_cmds()

    def _shebang_line(self):
        loader_path = os.path.join(self.graphene, 'Runtime', 'pal_loader')
        line = '#!%s SGX\n' % loader_path
        return line

    #------------------------------------------------------
    # public api
    #------------------------------------------------------

    def make(self):
        with open(self.inpath) as f:
            for line in f.readlines():
                self.linenum += 1
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                args = line.split()
                name = args.pop(0)
                if name not in self._directive_table.keys():
                    self._parse_err('unknown directive \"%s\"', name)
                directive = self._directive_table[name]
                nargs = len(args)
                if not directive.varargs:
                    if nargs != directive.nargs:
                        self._parse_err('directive \"%s\" takes %d args, but %d given',
                                directive.nargs, nargs)
                else:
                    if nargs < directive.nargs:
                        self._parse_err('directive \"%s\" needs at least %d args, but only %d given',
                                directive.nargs, nargs)
                directive.fn(*args)  

        self._postprocess()
        self.out.sort()

        _mkdir_p(os.path.dirname(self.out_manifest))
        with open(self.out_manifest, 'wb') as f:
            f.write(self._shebang_line())
            for line in self.out:
                f.write(line + '\n')

def main(argv):
    shortopts = 'hg:o:v'
    longopts = ['help', 'graphene=', 'output=', 'verbose']
    # options
    global verbose
    out_manifest = None
    graphene = '/usr/src/graphene'
    # arguments
    conf = None

    try:
        opts, args = getopt.getopt(argv[1:], shortopts, longopts)
    except getopt.GetoptError as err:
        sys.stderr.write('%s\n', str(errr))
        _usage(1)

    for o, a in opts:
        if o in ('-h', '--help'):
            _usage(0)
        elif o in ('-g', '--graphene'):
            graphene = a
        elif o in ('-o', '--output'):
            out_manifest = a
        elif o in ('-v', '--verbose'):
            verbose = True
        else:
            assert False, "unhandled option '%s'" % o
    
    if len(args) != 1:
        _usage(1)

    conf = args[0]
    if not out_manifest:
        out_manifest = '%s.manifest.sgx' % conf

    ManifestMaker(graphene, conf, out_manifest).make()

if __name__ == '__main__':
    main(sys.argv)
