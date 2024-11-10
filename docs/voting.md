شرح قرارداد: قرارداد Voting شامل ساختارهایی برای پروپوزال‌ها و رأی‌گیری است.
توابع اصلی:
createProposal: ایجاد پروپوزال جدید توسط ادمین.
vote: ثبت رأی برای پروپوزال.
getProposal: دریافت جزئیات پروپوزال.
متغیرها:
admin: آدرس ادمین.
proposals: نگهداری پروپوزال‌ها.
votes: ثبت رأی‌های انجام‌شده.


قرارداد Voting
شرح: قرارداد Voting برای ایجاد و مدیریت پروپوزال‌های رأی‌گیری و جمع‌آوری آرا پیاده‌سازی شده است.

مراحل استقرار و تست
استقرار قرارداد:
قرارداد Voting با موفقیت مستقر شد و حساب مالک به عنوان مدیر قرارداد تعیین شد.

javascript
Copy code
const Voting = await artifacts.require("Voting").deployed();
ایجاد پروپوزال جدید:
یک پروپوزال رأی‌گیری جدید توسط مدیر ایجاد شد.

javascript
Copy code
await Voting.createProposal("Project Investment Proposal", { from: accounts[0] });
ثبت رأی برای پروپوزال:
رأی‌دهندگان با موفقیت به پروپوزال رأی دادند و نتایج در قرارداد ثبت شد.

javascript
Copy code
await Voting.vote(1, { from: accounts[1] });
بررسی نتایج پروپوزال:
اطلاعات و نتایج پروپوزال به درستی بازیابی شد.

javascript
Copy code
const proposal = await Voting.getProposal(1);
console.log("Proposal Details:", proposal);
