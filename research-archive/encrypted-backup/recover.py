import hashlib,json,pathlib,sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
root=pathlib.Path(__file__).resolve().parent
key=pathlib.Path(sys.argv[1]).read_bytes()
manifest=json.loads((root/'manifest.json').read_text())
cipher=AESGCM(key);digest=hashlib.sha256()
with open(sys.argv[2],'xb') as out:
 for item in manifest['parts']:
  encrypted=(root/item['file']).read_bytes()
  if hashlib.sha256(encrypted).hexdigest()!=item['sha256']:raise ValueError('Encrypted part checksum mismatch')
  plain=cipher.decrypt(encrypted[:12],encrypted[12:],item['file'].encode())
  digest.update(plain);out.write(plain)
if digest.hexdigest()!=manifest['bundle_sha256']:raise ValueError('Bundle checksum mismatch')
print('Restored bundle verified.')
