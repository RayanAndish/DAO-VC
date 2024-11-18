import json
import os
import time
from collections import Counter
from DAO_Hash_Func import custom_hash  # فرض می‌کنیم تابع هش شما در فایل DAO_VC_Hash.py قرار دارد

def test_collision_resistance():
    """تست مقاومت در برابر تصادم"""
    input_data1 = "Test Input 1"
    input_data2 = "Test Input 2"
    salt = b"static_salt_16_byte"  # استفاده از Salt ثابت 16 بایتی
    hash1 = custom_hash(input_data1, salt)
    hash2 = custom_hash(input_data2, salt)
    return hash1 != hash2

def test_preimage_resistance(target_hash):
    # تست مقاومت در برابر پیش تصویر
    print("Running Pre-image Resistance Test...")
    for _ in range(100000):  # تلاش برای یافتن ورودی مطابق هش
        input_data = os.urandom(32)
        if custom_hash(input_data) == target_hash:
            return {"success": False, "found_input": input_data.hex()}
    return {"success": True}

def test_second_preimage_resistance(target_input):
    # تست مقاومت در برابر پیش‌تصویر دوم
    print("Running Second Pre-image Resistance Test...")
    salt = b"static_salt_16_byte"  # استفاده از Salt ثابت 16 بایتی
    target_hash = custom_hash(target_input, salt)
    for _ in range(10000):  # تلاش برای یافتن ورودی دیگر با همان هش
        random_input = os.urandom(32)
        if random_input != target_input and custom_hash(random_input, salt) == target_hash:
            return {"success": False, "found_input": random_input.hex()}
    return {"success": True}

def test_avalanche_effect():
    """تست اثر بهمن"""
    input_data = "Test Input"
    salt = b"static_salt_16_byte"  # استفاده از Salt ثابت 16 بایتی
    hash1 = custom_hash(input_data, salt)
    hash2 = custom_hash(input_data + " ", salt)  # تغییر کوچک در ورودی

    # محاسبه هامینگ‌دیستنس بین هش‌ها
    hamming_distance = sum(bin(x ^ y).count('1') for x, y in zip(bytes.fromhex(hash1[2:]), bytes.fromhex(hash2[2:])))
    return hamming_distance

def test_performance():
    # تست عملکرد
    print("Running Performance Test...")
    start_time = time.time()
    for _ in range(10000):
        custom_hash(os.urandom(32), b"static_salt_16_byte")
    elapsed_time = time.time() - start_time
    return {"hashes_per_second": 10000 / elapsed_time}

def test_uniform_distribution():
    # تست توزیع یکنواخت
    print("Running Uniform Distribution Test...")
    bit_count = Counter()
    for _ in range(10000):
        hash_result = custom_hash(os.urandom(32), b"static_salt_16_byte")
        bit_count.update(bin(int(hash_result, 16))[2:])
    total_bits = sum(bit_count.values())
    zero_ratio = bit_count['0'] / total_bits
    one_ratio = bit_count['1'] / total_bits
    return {"zero_ratio": zero_ratio, "one_ratio": one_ratio, "success": abs(zero_ratio - 0.5) < 0.05}

def main():
    # فایل خروجی نتایج تست
    result_file = "./test_results.json"
    results = {}

    # اجرای تست‌ها
    results["collision_resistance"] = test_collision_resistance()
    results["preimage_resistance"] = test_preimage_resistance("0" * 64)
    results["second_preimage_resistance"] = test_second_preimage_resistance(b"target_input")
    results["avalanche_effect"] = test_avalanche_effect()
    results["performance"] = test_performance()
    results["uniform_distribution"] = test_uniform_distribution()

    # ذخیره نتایج به فایل JSON
    with open(result_file, "w") as file:
        json.dump(results, file, indent=4)
    print(f"Test results saved to {result_file}")

if __name__ == "__main__":
    main()