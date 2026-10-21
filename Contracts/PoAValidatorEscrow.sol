// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PoAValidatorEscrow
 * @dev Manages bonded validator collateral, admission weighting, and AI-driven slashing (Eqs. 1 & 11)
 */
contract PoAValidatorEscrow {
    address public governanceAdmin;
    uint256 public constant MIN_COLLATERAL = 1000 ether; // 1,000 tokens min stake
    uint256 public totalBondedCollateral;

    struct Validator {
        uint256 bondedStake;
        uint256 historicalPerformance; // Performance coefficient (scaled 1e4)
        bool isActive;
        bool isBlacklisted;
    }

    mapping(address => Validator) public validators;
    address[] public activeValidatorList;

    event ValidatorBonded(address indexed validator, uint256 amount);
    event ValidatorSlashed(address indexed validator, uint256 slashedAmount, uint256 remainingStake, uint256 anomalyScore);
    event ValidatorEjected(address indexed validator, string reason);

    modifier onlyAdmin() {
        require(msg.sender == governanceAdmin, "Unauthorized: caller is not admin");
        _;
    }

    constructor() {
        governanceAdmin = msg.sender;
    }

    function depositCollateral() external payable {
        require(msg.value >= MIN_COLLATERAL, "Insufficient collateral threshold");
        require(!validators[msg.sender].isBlacklisted, "Validator address is blacklisted");

        if (!validators[msg.sender].isActive) {
            validators[msg.sender].isActive = true;
            validators[msg.sender].historicalPerformance = 10000; // Baseline 1.0 (10000 bps)
            activeValidatorList.push(msg.sender);
        }

        validators[msg.sender].bondedStake += msg.value;
        totalBondedCollateral += msg.value;

        emit ValidatorBonded(msg.sender, msg.value);
    }

    function slashValidator(address validator, uint256 anomalyBps) external onlyAdmin {
        require(validators[validator].isActive, "Target node is not active");
        require(anomalyBps <= 10000, "Invalid anomaly bounds");

        uint256 currentStake = validators[validator].bondedStake;
        uint256 slashAmount = (currentStake * anomalyBps) / 10000;
        uint256 newStake = currentStake - slashAmount;

        validators[validator].bondedStake = newStake;
        totalBondedCollateral -= slashAmount;

        payable(address(0)).transfer(slashAmount);

        emit ValidatorSlashed(validator, slashAmount, newStake, anomalyBps);

        if (anomalyBps >= 7000 || newStake < MIN_COLLATERAL) {
            validators[validator].isActive = false;
            validators[validator].isBlacklisted = true;
            emit ValidatorEjected(validator, "Anomaly threshold exceeded or stake exhausted");
        }
    }

    function getValidatorCount() external view returns (uint256) {
        return activeValidatorList.length;
    }
}