# مستند قراردادهای پروژه DAO-VC

## 1. قرارداد توکن (Token)
**پارامترهای کلیدی و تست‌ها:**

### موجودی اولیه توکن:
مقدار اولیه باید به صاحب قرارداد یا DAO منتقل شده باشد.

`const balance = await Token.balanceOf(daoAddress);`
`console.log("Initial Token Balance for DAO:", balance.toString());`

### انتقال توکن با کارمزد پویا:
انتقال توکن بین حساب‌ها را با اعمال کارمزدها بررسی کنید.

`await Token.transfer(accounts[2], 1000, { from: daoAddress });`
`const recipientBalance = await Token.balanceOf(accounts[2]);`
`console.log("Recipient Balance:", recipientBalance.toString());`

### نرخ تبدیل:
نرخ تبدیل توکن با استفاده از اوراکل را بررسی کنید.

`const exchangeRate = await Token.getExchangeRate("0xAddressOfAnotherToken");`
`console.log("Exchange Rate:", exchangeRate.toString());`

### مستندسازی:
در مستند، نتایج تست برای موجودی اولیه، کارمزدها، و نرخ تبدیل ثبت می‌شود.
جزئیات نحوه تغییر و تنظیم کارمزد‌ها و آدرس دریافت‌کننده کارمزدها در قرارداد توکن مستند شود.

---

## 2. قرارداد رأی‌گیری (Voting)
**پارامترهای کلیدی و تست‌ها:**

### ایجاد پروپوزال:
بررسی کنید که پروپوزال‌ها به درستی ایجاد شده و در شمارش کلی ثبت می‌شوند.

`await Voting.createProposal("Investment Proposal 1", { from: daoAddress });`
`const proposal = await Voting.getProposal(1);`
`console.log("Proposal Details:", proposal);`

### رأی‌دهی با کارمزد:
صحت رأی‌دهی و اعمال کارمزدها برای کاربران مختلف را بررسی کنید.

`await Voting.vote(1, true, { from: accounts[2], value: web3.utils.toWei("0.01", "ether") });`
`const proposalResult = await Voting.getProposalResult(1);`
`console.log("Proposal Vote Counts:", proposalResult);`

### تنظیم نرخ کارمزد پویا:
با استفاده از حساب DAO، نرخ کارمزد‌ها را تغییر داده و اثرات آن را بررسی کنید.

`await Voting.setVotingFeeRate(2, { from: daoAddress });`

### مستندسازی:
نتایج تست ایجاد پروپوزال‌ها، رأی‌دهی و اعمال کارمزدها با ذکر نرخ کارمزدها و تغییرات به‌دست‌آمده مستند شود.

---

## 3. قرارداد اجماع (Consensus)
**پارامترهای کلیدی و تست‌ها:**

### افزودن اعتبارسنج:
اعتبارسنج جدیدی اضافه کنید و صحت اضافه‌شدن را بررسی کنید.

`await Consensus.addValidator(accounts[3], 1000, { from: daoAddress });`
`const isValidator = await Consensus.isValidator(accounts[3]);`
`console.log("Is Account 3 Validator:", isValidator);`

### رأی‌دهی اعتبارسنج‌ها:
رأی‌دهی توسط اعتبارسنج‌ها و اعمال تغییرات بر پروپوزال‌ها بررسی شود.

`await Consensus.voteProposal(1, true, { from: accounts[3] });`
`const proposalResult = await Consensus.getProposalResult(1);`
`console.log("Consensus Proposal Result:", proposalResult);`

### مستندسازی:
نتایج و جزئیات تست اعتبارسنجی، اضافه کردن اعتبارسنج‌ها و بررسی وضعیت نهایی پروپوزال‌ها در مستند ذکر شود.
