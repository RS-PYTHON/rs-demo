# FTPES Demo Setup with Custom CA, Server, and Client Certificates

This document describes how to set up a demo FTPES server with a custom Certificate Authority (CA), server certificate, and client certificate. It includes complete instructions for generating certificates, setting up directories, and using them in Python with `ftplib.FTP_TLS`.

---

## Directory Structure

```
rs-demo/local-mode/certs/
├── ca.crt       # CA certificate
├── client.crt   # client certificate
├── client.key   # client private key
├── server.crt   # server certificate
├── server.key   # server private key
```

- `ca.crt` → used by client to verify the server
- `client.crt` + `client.key` → used by client for mutual TLS authentication
- `server.crt` + `server.key` → used by the server for TLS

---

## OpenSSL Configuration File

Save this as `openssl.cnf`:

```ini
[ ca ]
default_ca = CA_default

[ CA_default ]
dir               = ./demoCA
certs             = $dir/certs
crl_dir           = $dir/crl
new_certs_dir     = $dir/newcerts
database          = $dir/index.txt
serial            = $dir/serial
RANDFILE          = $dir/private/.rand

private_key       = $dir/private/ca.key
certificate       = $dir/certs/ca.crt

default_md        = sha256
name_opt          = ca_default
cert_opt          = ca_default
default_days      = 3650
preserve          = no
policy            = policy_strict

[ policy_strict ]
countryName             = optional
stateOrProvinceName     = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ req ]
default_bits        = 4096
distinguished_name  = req_distinguished_name
string_mask         = utf8only
default_md          = sha256
x509_extensions     = v3_ca

[ req_distinguished_name ]
countryName                     = Country Name (2 letter code)
countryName_default             = XX
stateOrProvinceName             = State or Province Name
stateOrProvinceName_default     = GenericState
localityName                    = Locality Name
localityName_default            = GenericCity
organizationName                = Organization Name
organizationName_default        = MyOrg
organizationalUnitName          = Organizational Unit Name
organizationalUnitName_default  = Dev
commonName                      = Common Name
commonName_max                  = 64
emailAddress                    = Email Address
emailAddress_max                = 64

[ v3_ca ]
basicConstraints        = critical,CA:TRUE
keyUsage                = critical,keyCertSign,cRLSign
subjectKeyIdentifier    = hash
authorityKeyIdentifier  = keyid:always,issuer:always

[ v3_server ]
basicConstraints        = CA:FALSE
keyUsage                = digitalSignature,keyEncipherment
extendedKeyUsage        = serverAuth
subjectKeyIdentifier    = hash
authorityKeyIdentifier  = keyid,issuer
subjectAltName          = @alt_names

[ v3_client ]
basicConstraints        = CA:FALSE
keyUsage                = digitalSignature,keyEncipherment
extendedKeyUsage        = clientAuth
subjectKeyIdentifier    = hash
authorityKeyIdentifier  = keyid,issuer

[ alt_names ]
DNS.1 = ftpserver
```
---

## Step 1: Create CA Directories

```bash
mkdir -p demoCA/{certs,crl,newcerts,private}
touch demoCA/index.txt
echo 1000 > demoCA/serial
```

This sets up the folder structure for the CA and necessary files for OpenSSL to track certificates.

---

## Step 2: Generate CA Certificate

```bash
openssl req -x509 -new -nodes \
  -keyout demoCA/private/ca.key \
  -out demoCA/certs/ca.crt \
  -sha256 -days 3650 \
  -config openssl.cnf \
  -extensions v3_ca
```

- `ca.crt` → CA public certificate
- `ca.key` → CA private key

This ensures the CA has the correct **key usage** and **authority key identifier**.

---

## Step 3: Generate Server Certificate

### 3a: Create Server Private Key

```bash
openssl genpkey -algorithm RSA -out server.key -pkeyopt rsa_keygen_bits:2048
```

### 3b: Create Server CSR

```bash
openssl req -new -key server.key -out server.csr \
  -subj "/CN=ftpserver" \
  -config openssl.cnf
```

### 3c: Sign Server Certificate with CA

```bash
openssl x509 -req -in server.csr \
  -CA demoCA/certs/ca.crt -CAkey demoCA/private/ca.key -CAcreateserial \
  -out server.crt -days 365 -sha256 \
  -extfile openssl.cnf -extensions v3_server
```

- `server.crt` → certificate for the server
- `server.key` → server private key

This ensures **AKI, SKI, and SAN** are properly set.

---

## Step 4: Generate Client Certificate

### 4a: Create Client Private Key

```bash
openssl genpkey -algorithm RSA -out client.key -pkeyopt rsa_keygen_bits:2048
```

### 4b: Create Client CSR

```bash
openssl req -new -key client.key -out client.csr \
  -subj "/CN=ftpclient" \
  -config openssl.cnf
```

### 4c: Sign Client Certificate with CA

```bash
openssl x509 -req -in client.csr \
  -CA demoCA/certs/ca.crt -CAkey demoCA/private/ca.key -CAcreateserial \
  -out client.crt -days 365 -sha256 \
  -extfile openssl.cnf -extensions v3_client
```

- `client.crt` → client certificate
- `client.key` → client private key

---

## Step 5: Copy Certificates to Application Folder

```bash
mkdir -p rs-demo/local-mode/certs
cp demoCA/certs/ca.crt rs-demo/local-mode/certs/ca.crt
cp client.crt rs-demo/local-mode/certs/client.crt
cp client.key rs-demo/local-mode/certs/client.key
cp server.crt rs-demo/local-mode/certs/server.crt
cp server.key rs-demo/local-mode/certs/server.key
```

- These paths match what the Python client and server containers will use.

---

## Notes

- **Server container (`vsftpd`)** should map `server.crt`, `server.key`, and `ca.crt` only.
- **Client components** should map `ca.crt` and optionally `client.crt/client.key` for mutual TLS.
- Do not place `client.crt`/`client.key` on the server.
