#!/bin/bash

# generate 2048 bit RSA keypair; output private key
openssl genrsa -3 -out private.pem 3072

# export public key
#openssl rsa -in private.pem -outform PEM -pubout -out public.pem
