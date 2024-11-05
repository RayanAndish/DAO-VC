const HDWalletProvider = require('@truffle/hdwallet-provider');
require('dotenv').config();

module.exports = {
  networks: {
    // شبکه محلی برای تست با Ganache
    development: {
      host: "127.0.0.1",     // آدرس سرور Ganache یا IP سرور دیگر
      port: 8545,            // پورت پیش‌فرض Ganache
      network_id: "*"        // هر شبکه‌ای، برای تست محلی
    },
    // شبکه اصلی اتریوم یا تست‌نت (مانند Ropsten) برای استفاده آتی
    ropsten: {
      provider: () =>
        new HDWalletProvider(process.env.MNEMONIC, `https://ropsten.infura.io/v3/${process.env.INFURA_PROJECT_ID}`),
      network_id: 3,       // شناسه شبکه Ropsten
      gas: 5500000,        // محدودیت گس
      confirmations: 2,    // تعداد تایید‌ها برای انتقال
      timeoutBlocks: 200,  // تعداد بلاک‌ها برای زمان انتظار
      skipDryRun: true
    }
  },

  // تنظیمات کامپایلر
  compilers: {
    solc: {
      version: "0.8.0",       // نسخه Solidity
      settings: {             // تنظیمات بهینه‌سازی
        optimizer: {
          enabled: true,
          runs: 200
        }
      }
    }
  }
};
