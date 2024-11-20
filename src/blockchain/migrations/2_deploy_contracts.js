require("dotenv").config(); // دریافت متغیرهای محیطی
const Token = artifacts.require("Token");
const Voting = artifacts.require("Voting");
const HybridConsensus = artifacts.require("HybridConsensus"); // تغییر نام قرارداد به HybridConsensus

module.exports = async function (deployer, network, accounts) {
    // متغیرهای حساس و امنیتی
    const initialSupply = process.env.INITIAL_SUPPLY;
    const daoAddress = process.env.DAO_ADDRESS; // انتخاب حساب اول به عنوان آدرس DAO
    const votingFeeRate = process.env.VOTING_FEE_RATE; // مقدار کارمزد رأی‌دهی (در صدها)
    const feeCollector = process.env.FEE_COLLECTOR; // آدرس جمع‌آوری‌کننده کارمزدها


    // چک کردن آدرس DAO
    if (!web3.utils.isAddress(daoAddress) || !web3.utils.isAddress(feeCollector)) {
        throw new Error("Invalid address provided.");
    }

    // استقرار قرارداد توکن با پارامترهای امن
    await deployer.deploy(Token, initialSupply, daoAddress);
    const tokenInstance = await Token.deployed();
    console.log("Token deployed at address:", tokenInstance.address);

    // استقرار قرارداد Voting
    await deployer.deploy(Voting, votingFeeRate, feeCollector, daoAddress); // ارسال daoAddress به Voting
    const votingInstance = await Voting.deployed();
    console.log("Voting deployed at address:", votingInstance.address);

    // استقرار قرارداد HybridConsensus
    await deployer.deploy(HybridConsensus, daoAddress); // ارسال daoAddress به HybridConsensus
    const consensusInstance = await HybridConsensus.deployed();
    console.log("HybridConsensus deployed at address:", consensusInstance.address);

    // ذخیره اطلاعات قراردادها در یک فایل (اختیاری)
    const fs = require("fs");
    const deploymentInfo = {
        Token: tokenInstance.address,
        Voting: votingInstance.address,
        HybridConsensus: consensusInstance.address,
    };
    fs.writeFileSync("./deployment_info.json", JSON.stringify(deploymentInfo, null, 2));
};