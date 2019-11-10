Overview
========

Create a manifest to run an application on the
[Phoenix](https://github.com/smherwig/phoenix) SGX Microkernel.


makemanifest uses an input file (sometimes called a premanifest) that is a
simplified version of Graphene's manifiest syntax
([manifest-syntax](https://github.com/oscarlab/graphene/wiki/Graphene-Manifest-Syntax),
 [manifest-sgx-syntax](https://github.com/oscarlab/graphene/wiki/Graphene-SGX-Manifest-Syntax))
while also including directives specific to Phoenix.  Ultimately, makemanfiest
translates to Graphene Manifest format.


Installation
============

There is nothing to install; the repo simply must be cloned:


```
git clone https://github.com/smherwig/phoenix-makemanifest makemanifest
```

The script `pal-sgx-get-token` has a dependency on `pycrypto`

```
pip install pycrypto
```


Usage
=====

A user writes a `manifest.conf` file for the executable they wish to run on
Phoenix, and invokes `make_sgx.py` to convert `manifest.conf` into a manifest
suitable for Graphene/Phoenix's loader (`phoenix/Runtime/pal_loader`).  This
process is called *packaging*.  For instance, the command-line to package the
[nextfs](https://github.com/smherwig/phoenix-fileserver) fileserver to run on
Phoenix is:

```
cd ~/src/makemanifest
./make_sgx.py -g ~/src/phoenix -k ~/share/phoenix/enclave-key.pem -p ~/src/fileserver/deploy/manifest.conf -t $PWD -v -o nextfsserver
```

Under the hood, `make_sgx.py` calls:

- `make_manifest.py`: converts the premanifest to Graphene manifest format
- `pal-sgx-sign`: signs the Graphene manifest
- `pal-sgx-get-token`: extracts launch token


Files from Phoenix/Graphene
===========================

The makemanifest repo has copies of several files from the
[phoenix](https://github.com/smherwig/phoenix) repository.  A user does not
need to do anything with these files, but  maintainer must
ensure that these files are in-sync with phoenix as the phoenix source changes:

```
cd ~/src/makemanifest

cp ~/src/phoenix/Pal/src/host/Linux-SGX/signer/aesm_pb2.py .
cp ~/src/phoenix/Pal/src/host/Linux-SGX/signer/aesm.proto .
cp ~/src/phoenix/Pal/src/host/Linux-SGX/signer/pal-sgx-get-token .
cp ~/src/phoenix/Pal/src/host/Linux-SGX/signer/pal-sgx-sign .
cp ~/src/phoenix/Pal/src/host/Linux-SGX/generated_offsets.py .
```

Note that `generated_offsets.py` is only present after building phoenix.


Manifest Syntax and Directives
==============================

URI refers to a URI on the host machine.


`CAFILE`
--------

Syntax:

```
CAFILE <pem_file>
```

Translates to:

```
phoenix.ca_der = DER_HEX
```

Example:

```
CAFILE config/root.crt
```


`DEBUG`
-------

Specify whether Graphene should run with debug logging on or off.

```
DEBUG on|off
```

For *on*, this translate to:

```
loader.debug_type = inline
```

For *off*, this translate to:

```
loader.debug_type = none
```


`ENCLAVE_SIZE`
--------------

Specify the maximum memory for the enclave.  The enclave size is in
mebibytes, and must be a power of two.

```
ENCLAVE_SIZE <size_mb>
```

Translates to

```
sgx.enclave_size = <size_mb>M
```


`EXEC`
------

Specify the executable to run on Graphene.

Syntax:

```
EXEC <path>
```

Translates to:

```
loader.exec = <absolute(path)>
loader.execname = <basename(path)>
```

Example:

```
EXEC file:/usr/bin/python
```

In addition, any dependencies of the executable (as per `ldd`) are added
as trusted files (that is, as `sgx.trusted_files.` Graphene directives).



`MODULE`
--------

Specify a shared object that the executable might load at runtime (as with
`dlopen`).

Syntax: 

```
MODULE <host_uri> 
```

Translates to the Graphene directives:

```
sgx.trusted_files.<basename(host_uri)> = <host_uri>
```

Example:

```
MODULE file:/lib/x86_64-linux-gnu/libnss_dns.so.2
```

In addition, any dependencies of the shared library (as per `ldd`) are also
added as trusted files.



`MOUNT`
-------

### chroot

```
MOUNT <server_urih> <graphene_mountpoint> chroot ro|rw
```

### nextfs

```
MOUNT <server_uri> <graphene_mountpoint> nextfs
```

### smdish

Also called sm-vericrypt-simple.

```
MOUNT <server_uri> <graphene_mountpoint> smdish
```


### smuf

Also called sm-vericrypt.


```
MOUNT <server_uri,memdir_uri> <graphene_server_mountpoint,graphene_memdir_mountpoint> smuf
```

### smc

Also called sm-crypt.

```
MOUNT <memdir_uri> <graphene_smc_mountpoint,graphene_memdir_mountpoint> smc
```


`THREADS`
---------

Specify the maximum number of enclave threads.  If *exitless* is also
specified, the threads issue exitless system calls.


Syntax:

```
THREADS <num> [exitless]
```

Translates to:

```
sgx.thread_num = NUM
```

If *exitless* is spcifies, also adds the Graphene directive:

```
sgx.rpc_thread_num = NUM
```

Example:

```
THREADS 2
```



`TIMESERVER`
------------

Specifies that time-related system calls should proxy to a timeserver.

Syntax:

```
TIMESERVER <URI> <PUBLIC_KEY_PEM_PATH> <PERCENT_CALLS>
```

`URI` is the URI for the timeserver, and must start with `udp:`.
`PUBLIC_KEY_PEM_PATH` is the path to the timeserver's public key, in PEM
format.  `PERCENT_CALLS` is the percentage of calls to direct to the timesever.
For instance, if `1`, Graphene proxies all time-related system calls to the
timeserver; if `0.5`, Graphene proxies half of the calls.


Example:

```
TIMESERVER udp:127.0.0.1:12345 /home/smherwig/src/timeserver/public.pem 1
```
