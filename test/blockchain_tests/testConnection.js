require('dotenv').config();
const Web3 = require('web3');

// دریافت RPC_URL و PRIVATE_KEY از فایل .env
const rpcUrl = process.env.RPC_URL;
const privateKey = process.env.PRIVATE_KEY;

// ایجاد اتصال به شبکه با Web3
const web3 = new Web3(new Web3.providers.HttpProvider(rpcUrl));

const testConnection = async () => {
  try {
    // نمایش شماره نسخه شبکه برای تست اتصال
    const networkId = await web3.eth.net.getId();
    console.log(`Connected to network ID: ${networkId}`);

    // بررسی تعداد حساب‌ها برای اطمینان از دسترسی
    const accounts = await web3.eth.getAccounts();
    console.log("Accounts on the network:", accounts);

    // انجام تراکنش آزمایشی
    const balance = await web3.eth.getBalance(accounts[0]);
    console.log(`Balance of first account: ${web3.utils.fromWei(balance, 'ether')} ETH`);

    console.log("Connection test successful!");
  } catch (error) {
    console.error("Connection test failed:", error);
  }
};

testConnection();
