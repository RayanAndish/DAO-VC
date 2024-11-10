شرح قرارداد: قرارداد اجماع شامل نودهای تأییدکننده و توابع اضافه/حذف نود است.
توابع اصلی:
addValidator: اضافه کردن نود به عنوان تأییدکننده.
removeValidator: حذف نود تأییدکننده.
isValidator: بررسی تأییدکننده بودن یک آدرس.
متغیرها:
validators: ذخیره نودهای تأییدکننده.
validatorList: لیست نودهای تأییدکننده.


قرارداد Consensus
شرح: قرارداد Consensus برای مدیریت و بررسی اعتبارسنج‌ها و فرآیند اجماع پیاده‌سازی شده است.

مراحل استقرار و تست
استقرار قرارداد:
قرارداد Consensus با موفقیت مستقر شد و حساب مدیر به عنوان مالک تعیین شد.

javascript
Copy code
const Consensus = await artifacts.require("Consensus").deployed();
افزودن اعتبارسنج جدید:
حساب‌های جدید به عنوان اعتبارسنج به شبکه اضافه شدند.

javascript
Copy code
await Consensus.addValidator(accounts[1], { from: accounts[0] });
بررسی وضعیت اعتبارسنج:
اعتبارسنج‌ها با موفقیت شناسایی و ثبت شدند.

javascript
Copy code
const isValidator = await Consensus.isValidator(accounts[1]);
console.log("Is Validator:", isValidator); // انتظار مقدار: true
حذف اعتبارسنج:
اعتبارسنج با موفقیت از شبکه حذف شد و بررسی نتیجه موفقیت‌آمیز بود.

javascript
Copy code
await Consensus.removeValidator(accounts[1], { from: accounts[0] });
const isValidatorAfterRemoval = await Consensus.isValidator(accounts[1]);
console.log("Is Validator After Removal:", isValidatorAfterRemoval); // انتظار مقدار: false
