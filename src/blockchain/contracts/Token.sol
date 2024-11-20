// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@chainlink/contracts/src/v0.8/interfaces/AggregatorV3Interface.sol"; // این خط برای اتصال به اوراکل Chainlink استفاده می‌شود

contract Token is ERC20, Ownable {
    uint256 public transactionFeeRate = 1; // نرخ کارمزد اولیه
    address public feeCollector; // آدرس دریافت‌کننده کارمزد
    address public daoAddress; // آدرس قرارداد DAO برای تایید دسترسی‌ها

    mapping(address => uint256) public customFeeRates;
    mapping(address => address) public oracleAddresses;

    constructor(uint256 initialSupply, address _daoAddress) ERC20("Rayan Andish Token", "RATK") Ownable(msg.sender) {
        _mint(msg.sender, initialSupply);
        feeCollector = msg.sender;
        daoAddress = _daoAddress;
    }

    modifier onlyDAO() {
        require(msg.sender == daoAddress, "Only DAO can execute this action");
        _;
    }

    // تنظیم نرخ کارمزد پویا برای کاربر خاص توسط DAO
    function setCustomFeeRate(address account, uint256 feeRate) external onlyDAO {
        require(feeRate <= 5, "Custom fee rate cannot exceed 5%");
        customFeeRates[account] = feeRate;
    }

    // تنظیم کارمزد کلی توسط DAO
    function setTransactionFeeRate(uint256 feeRate) external onlyDAO {
        require(feeRate <= 5, "Fee rate cannot exceed 5%");
        transactionFeeRate = feeRate;
    }

    // تنظیم آدرس دریافت‌کننده کارمزد توسط DAO
    function setFeeCollector(address collector) external onlyDAO {
        feeCollector = collector;
    }

    // تابع انتقال توکن با کارمزد پویا
    function transfer(address recipient, uint256 amount) public override returns (bool) {
        uint256 feeRate = customFeeRates[msg.sender] > 0 ? customFeeRates[msg.sender] : transactionFeeRate;
        uint256 fee = (amount * feeRate) / 100;
        uint256 amountAfterFee = amount - fee;

        super.transfer(feeCollector, fee);
        return super.transfer(recipient, amountAfterFee);
    }

    // تنظیم آدرس اوراکل برای جفت توکن‌های مختلف
    function setOracleAddress(address tokenAddress, address oracleAddress) external onlyDAO {
        oracleAddresses[tokenAddress] = oracleAddress;
    }

    // دریافت نرخ تبدیل از اوراکل Chainlink
    function getExchangeRate(address tokenAddress) public view returns (uint256) {
        address oracle = oracleAddresses[tokenAddress];
        require(oracle != address(0), "Oracle not set for this token");

        AggregatorV3Interface priceFeed = AggregatorV3Interface(oracle);
        (, int price, , , ) = priceFeed.latestRoundData();
        require(price > 0, "Invalid price from oracle");

        return uint256(price);
    }

    // تبدیل توکن‌ها با استفاده از نرخ اوراکل و انتقال به کاربر
    function exchangeToken(address tokenAddress, uint256 amount) public {
        uint256 rate = getExchangeRate(tokenAddress);
        uint256 tokenAmount = (amount * rate) / (10 ** 8); // تنظیم واحد برای سازگاری با دقت اوراکل

        // انتقال توکن معادل به کاربر
        require(IERC20(tokenAddress).transfer(msg.sender, tokenAmount), "Transfer failed");
    }
}