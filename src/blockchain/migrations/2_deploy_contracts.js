const Token = artifacts.require("./contracts/Token");
const Voting = artifacts.require("./contracts/Voting");
const Consensus = artifacts.require("./contracts/Consensus");

module.exports = function (deployer) {
  deployer.deploy(Token, 1000000);       // مقدار اولیه توکن‌ها
  deployer.deploy(Voting);               // استقرار قرارداد Voting
  deployer.deploy(Consensus);            // استقرار قرارداد Consensus
};
