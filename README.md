Overview
========

Create a Phoenix manifest to run an application.


Files from Phoenix/Graphene
===========================

The makemanifest repo contains copies of a number of files in the Phoenix
repository: 

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

`CAFILE`
--------

```
CAFILE PEM_FILE
```

Translates to

```
phoenix.ca_der = DER_HEX
```


`DEBUG`
-------

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

```
ENCLAVE_SIZE <SIZE_MB>
```

Translates to

```
sgx.enclave_size = <SIZE_MB>M
```


`EXEC`
------

```
EXEC PATH
```

Translates to

```
loader.exec = ABSOLUTE_PATH
loader.execname = BASENAME_PATH
```


`MODULE`
--------


`MOUNT`
-------


`THREADS`
---------

```
THREADS <NUM> [exitless]
```

Translates to:

```
sgx.thread_num = NUM
```

If exitless is given, also adds

```
sgx.rpc_thread_num = NUM
```



`TIMESERVER`
------------

