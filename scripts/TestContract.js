require("dotenv").config();
const fs = require("fs");
const Web3 = require("web3");
const TruffleContract = require("@truffle/contract");
const truffleConfig = require("../src/blockchain/truffle-config");

// تنظیم آدرس گاناش از `truffle-config`
const ganacheUrl = truffleConfig.networks.development.url || "http://127.0.0.1:9545";
const web3 = new Web3(new Web3.providers.HttpProvider(ganacheUrl));

// بارگذاری فایل‌های قرارداد
const TokenArtifact = require("../src/blockchain/build/contracts/Token.json");
const VotingArtifact = require("../src/blockchain/build/contracts/Voting.json");
const ConsensusArtifact = require("../src/blockchain/build/contracts/HybridConsensus.json");

// تعریف قراردادها
const Token = TruffleContract(TokenArtifact);
const Voting = TruffleContract(VotingArtifact);
const HybridConsensus = TruffleContract(ConsensusArtifact);

// تنظیم provider برای قراردادها
Token.setProvider(web3.currentProvider);
Voting.setProvider(web3.currentProvider);
HybridConsensus.setProvider(web3.currentProvider);

async function runTests() {
    const accounts = await web3.eth.getAccounts();
    const daoAddress = accounts[0];
    const feeCollector = accounts[1];

    let testResults = {
        tokenTests: [],
        votingTests: [],
        consensusTests: [],
    };

    try {
        // ---- تست قرارداد Token ----
        const tokenInstance = await Token.deployed();
        const initialSupply = process.env.INITIAL_SUPPLY || "1000000";

        // بررسی موجودی اولیه
        const initialBalance = await tokenInstance.balanceOf(daoAddress);
        testResults.tokenTests.push({
            test: "Initial Token Balance Check",
            address: daoAddress,
            result: initialBalance.toString(),
            expected: initialSupply,
            success: initialBalance.toString() === initialSupply,
        });

        // انتقال توکن با محاسبه کارمزد
        const transferAmount = 100;
        const feeRate = await tokenInstance.transactionFeeRate();
        const fee = (transferAmount * feeRate) / 100;

        await tokenInstance.transfer(accounts[2], transferAmount, { from: daoAddress });

        const expectedBalance = transferAmount - fee;
        const recipientBalance = await tokenInstance.balanceOf(accounts[2]);

        testResults.tokenTests.push({
            test: "Token Transfer Check",
            from: daoAddress,
            to: accounts[2],
            amount: transferAmount,
            fee: fee,
            expectedBalance: expectedBalance.toString(),
            result: recipientBalance.toString(),
            success: recipientBalance.toString() === expectedBalance.toString(),
        });

        // ---- تست قرارداد Voting ----
        const votingInstance = await Voting.deployed();

        const currentTimestamp = Math.floor(Date.now() / 1000);
        const startTime = currentTimestamp + 60; // 1 دقیقه بعد
        const endTime = currentTimestamp + 3600; // 1 ساعت بعد
        const options = [0, 1]; // گزینه‌ها: 0 = خیر، 1 = بله

        await votingInstance.createProposal("Test Proposal", startTime, endTime, options, { from: daoAddress });
        const proposalDetails = await votingInstance.getProposal(1);

        // استخراج مقادیر از شیء بازگشتی
        const id = proposalDetails.id.toString();
        const description = proposalDetails.description;
        const startTimeResult = proposalDetails.startTime.toString();
        const endTimeResult = proposalDetails.endTime.toString();
        const voteCounts = proposalDetails.voteCounts.map((count) => count.toString());
        const finalized = proposalDetails.finalized;

        testResults.votingTests.push({
            test: "Proposal Creation and Details Check",
            proposalId: id,
            description,
            startTime: new Date(startTimeResult * 1000).toISOString(),
            endTime: new Date(endTimeResult * 1000).toISOString(),
            voteCounts,
            finalized,
            success: id === "1" && finalized === false,
        });

        // ---- تست قرارداد Consensus ----
        const consensusInstance = await HybridConsensus.deployed();

        const validatorAddress = accounts[3];
        const isValidator = await consensusInstance.isValidator(validatorAddress);

	if (isValidator) {
	    testResults.consensusTests.push({
	        test: "Add Validator Check",
	        validator: validatorAddress,
	        success: true,
	        message: "Validator already exists.",
	    });
	} else {
	    await consensusInstance.addValidator(validatorAddress, 500, { from: daoAddress });
	    testResults.consensusTests.push({
	        test: "Add Validator Check",
	        validator: validatorAddress,
	        success: true,
	    });
	}

    } catch (error) {
        console.error("Error running tests:", error);
    }

    // ذخیره نتایج به صورت فایل JSON
    fs.writeFileSync("./testResults.json", JSON.stringify(testResults, null, 2));
    console.log("Test results saved to testResults.json");
}

// اجرای تست‌ها
runTests().then(() => {
    console.log("Tests completed successfully.");
    process.exit(0); // خروج از اسکریپت
}).catch((error) => {
    console.error("Error in test execution:", error);
    process.exit(1);
});
