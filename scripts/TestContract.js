require("dotenv").config();
const fs = require("fs");
const Web3 = require("web3");
const truffleConfig = require("../src/blockchain/truffle-config");

// دریافت آدرس شبکه گاناش از `truffle-config.js`
const ganacheUrl = truffleConfig.networks.development.url || "http://127.0.0.1:9545";
const web3 = new Web3(ganacheUrl);

const Token = artifacts.require("../src/blockchain/contracts/Token");
const Voting = artifacts.require("../src/blockchain/contracts/Voting");
const HybridConsensus = artifacts.require("../src/blockchain/contracts/Consensus");

async function runTests() {
    const accounts = await web3.eth.getAccounts();
    const daoAddress = accounts[0]; // آدرس ادمین
    const feeCollector = accounts[1]; // آدرس جمع‌آوری کارمزد

    let testResults = {
        tokenTests: [],
        votingTests: [],
        consensusTests: [],
    };

    try {
        // تست‌های قرارداد Token
        const tokenInstance = await Token.deployed();

        // تست دریافت موجودی اولیه
        const initialBalance = await tokenInstance.balanceOf(daoAddress);
        testResults.tokenTests.push({
            test: "Initial Token Balance Check",
            address: daoAddress,
            result: initialBalance.toString(),
            success: initialBalance.toString() === process.env.INITIAL_SUPPLY
        });

        // انتقال توکن
        const transferAmount = 100;
        await tokenInstance.transfer(accounts[2], transferAmount, { from: daoAddress });
        const recipientBalance = await tokenInstance.balanceOf(accounts[2]);

        testResults.tokenTests.push({
            test: "Token Transfer Check",
            from: daoAddress,
            to: accounts[2],
            amount: transferAmount,
            result: recipientBalance.toString(),
            success: recipientBalance.toString() === transferAmount.toString()
        });

        // تست قرارداد Voting
        const votingInstance = await Voting.deployed();

        await votingInstance.createProposal("Project Proposal", { from: daoAddress });
        await votingInstance.vote(1, { from: accounts[2] });
        const proposal = await votingInstance.getProposal(1);

        testResults.votingTests.push({
            test: "Proposal Voting Check",
            proposal: proposal.description,
            votes: proposal.voteCount,
            success: proposal.voteCount.toString() === "1"
        });

        // تست قرارداد Consensus
        const consensusInstance = await HybridConsensus.deployed();

        await consensusInstance.addValidator(accounts[3], 500, { from: daoAddress });
        const isValidator = await consensusInstance.isValidator(accounts[3]);

        testResults.consensusTests.push({
            test: "Add Validator Check",
            validator: accounts[3],
            success: isValidator
        });

    } catch (error) {
        console.error("Error running tests:", error);
    }

    // ذخیره نتایج تست به صورت JSON
    fs.writeFileSync(
        "./testResults.json",
        JSON.stringify(testResults, null, 2)
    );

    console.log("Test results saved to testResults.json");
}

// اجرای تابع تست
runTests();
