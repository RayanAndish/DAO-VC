require("dotenv").config();
const express = require("express");
const Web3 = require("web3");
const Token = require("../blockchain/build/contracts/Token.json");
const Voting = require("../blockchain/build/contracts/Voting.json");
const Consensus = require("../blockchain/build/contracts/Consensus.json");


const app = express();
const web3 = new Web3(new Web3.providers.HttpProvider(process.env.RPC_URL));

const tokenContract = new web3.eth.Contract(Token.abi, Token.networks["5777"].address);
const votingContract = new web3.eth.Contract(Voting.abi, Voting.networks["5777"].address);
const consensusContract = new web3.eth.Contract(Consensus.abi, Consensus.networks["5777"].address);

app.use(express.json());

// API نمونه برای بررسی موجودی توکن
app.get("/api/token/balance/:address", async (req, res) => {
  try {
    console.log("Request for balance of address:", req.params.address); // لاگ جدید
    const balance = await tokenContract.methods.balanceOf(req.params.address).call({ gas: 8000000 });
    console.log("Balance retrieved:", balance); // لاگ جدید
    res.json({ balance });
  } catch (error) {
    console.error("Error retrieving balance:", error.message); // لاگ خطا
    res.status(500).json({ error: error.message });
  }
});

// APIهای دیگر برای رأی‌گیری و مدیریت DAO را به همین شکل اضافه کنید

app.listen(process.env.PORT, () => {
  console.log(`API Gateway running on port ${process.env.PORT}`);
});