شرح قرارداد: قرارداد توکن بر اساس استاندارد ERC-20 پیاده‌سازی شده و شامل امکاناتی برای تولید و سوزاندن توکن است.
توابع اصلی:
mint: تولید توکن جدید توسط مالک قرارداد.
burn: سوزاندن توکن توسط دارنده توکن.
متغیرها:
initialSupply: مقدار اولیه توکن‌ها.

قرارداد Token
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
