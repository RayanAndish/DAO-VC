گزارش استقرار و تست قراردادهای پروژه DAO-VC
مشخصات پروژه
پلتفرم: بلاکچین خصوصی DAO
قراردادهای اصلی: Token، Voting، Consensus
محیط تست: Ganache به عنوان شبکه تستی با استفاده از truffle console
۱. قرارداد Token
شرح: قرارداد Token یک توکن ERC20 را پیاده‌سازی می‌کند که دارای قابلیت ضرب و سوزاندن توکن توسط مالک است.

مراحل استقرار و تست
استقرار قرارداد:
قرارداد Token با موفقیت مستقر شد و مقدار اولیه توکن‌ها به آدرس مالک اختصاص داده شد.

javascript
Copy code
const Token = await artifacts.require("Token").deployed();
تست موجودی اولیه مالک:
موجودی اولیه به درستی به مالک اختصاص داده شد.

javascript
Copy code
const accounts = await web3.eth.getAccounts();
const ownerBalance = await Token.balanceOf(accounts[0]);
console.log("Owner Balance:", ownerBalance.toString()); // انتظار مقدار: 1000000
انتقال توکن:
تست انتقال موفقیت‌آمیز بود و تراکنش با موفقیت انجام شد.

javascript
Copy code
await Token.transfer(accounts[1], 1000, { from: accounts[0] });
۲. قرارداد Voting
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
۳. قرارداد Consensus
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
جمع‌بندی
تمامی قراردادها (Token, Voting, Consensus) با موفقیت مستقر شده و تست‌های عملکردی اولیه نیز موفقیت‌آمیز بودند. این مستند به عنوان گزارش اولیه استقرار و تست به پوشه مستندات پروژه اضافه شده و برای مراجعات آینده استفاده خواهد شد.