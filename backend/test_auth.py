import bcrypt

# Test password hashing and verification
password = "1234"
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
print(f"Generated hash: {hashed}")

# Test verification
result = bcrypt.checkpw(password.encode('utf-8'), hashed)
print(f"Verification result: {result}")

# Test with the hash in the database (as string)
db_hash = "$2b$12$MFlbL7pZ9DAcX2WhtiqTY.7aGS6XcSpfK2ezzpGhoRo0lUVTPU5Gu"
result2 = bcrypt.checkpw("1234".encode('utf-8'), db_hash.encode('utf-8'))
print(f"DB hash verification: {result2}")

# Test superadmin password
superadmin_hash = "$2b$12$fDaAQyBWz8Qjmh.MwY7Yz.muNfhED1z81LTL6Aow3SZzHFsC25LwK"
result3 = bcrypt.checkpw("superadmin123".encode('utf-8'), superadmin_hash.encode('utf-8'))
print(f"Superadmin hash verification: {result3}")
