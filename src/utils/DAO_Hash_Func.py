import struct
import hashlib
from Crypto.Cipher import AES
import hmac

# تابع پیش‌پردازش
def preprocess(data):
    """پیش‌پردازش داده‌ها"""
    if isinstance(data, bytes):
        data_bytes = data
    else:
        data_bytes = data.encode('utf-8')
    return data_bytes

# تابع هش اصلی با استفاده از HMAC
def custom_hash(data, salt=b"static_salt_16_byte"):
    """تابع هش سفارشی با بهبود اثر بهمن و افزودن Salt"""
    data = preprocess(data)

    # ترکیب داده‌ها با Salt
    salted_data = data + salt

    # عملیات اولیه AES
    aes = AES.new(salt[:16], AES.MODE_ECB)
    encrypted_data = aes.encrypt(salted_data.ljust(32)[:32])

    # چندین دور Keccak256
    for _ in range(5):  # افزایش تعداد دورها برای بهبود اثر بهمن
        hashed = hashlib.sha3_256(encrypted_data).digest()
        # ترکیب با داده‌های هش‌شده قبلی
        encrypted_data = bytes([x ^ y for x, y in zip(hashed, encrypted_data)])

    # عملیات HMAC برای افزایش امنیت
    hmac_key = b"some_secure_key"
    hmac_result = hmac.new(hmac_key, encrypted_data, hashlib.sha3_256).digest()

    # عملیات اختلاط نهایی
    hash_state = int.from_bytes(hmac_result, 'big')
    blocks = [salted_data[i:i + 32] for i in range(0, len(salted_data), 32)]
    for block in blocks:
        block_value = int.from_bytes(block.ljust(32, b'\x00'), 'big')  # پرکردن بلوک‌ها به اندازه 32 بایت
        hash_state ^= block_value
        hash_state = (hash_state * 0x5bd1e995) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        hash_state = (hash_state >> 13) | (hash_state << (256 - 13)) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

    # تبدیل به قالب هگزادسیمال
    return "0x" + hex(hash_state)[2:]

# تست الگوریتم
if __name__ == "__main__":
    test_data = "This is a test input for the custom hashing algorithm."
    hash_result = custom_hash(test_data)
    print("Hash Result:", hash_result)