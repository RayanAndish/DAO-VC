const HDWalletProvider = require('@truffle/hdwallet-provider');
require('dotenv').config();

module.exports = {
  networks: {
  development: {
    host: "127.0.0.1",  // آدرس IP سرور Ganache
    port: 9545,             // پورت Ganache
    network_id: "*",        // شبکه دلخواه
    gas: 8000000,           // افزایش Gas Limit
    gasPrice: 20000000000   // 20 gwei
  },
},
  // تنظیمات کامپایلر
  compilers: {
    solc: {
      version: "0.8.20",       // نسخه Solidity
      settings: {             // تنظیمات بهینه‌سازی
        optimizer: {
          enabled: true,
          runs: 200
        }
      }
    }
  }
};
