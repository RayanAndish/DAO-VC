// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PoAValidatorEscrow
 * @dev Manages bonded validator collateral, admission weighting, and AI-driven slashing (Eqs. 1 & 11)
 */
contract PoAValidatorEscrow {
    address public governanceAdmin;
    address payable public constant DEAD_ADDRESS = payable(0x000000000000000000000000000000000000dEaD);
    uint256 public constant MIN_COLLATERAL = 1000 ether;
    uint256 public constant ANOMALY_EJECTION_THRESHOLD = 6500; // Calibrated 0.65 threshold (matching Eq. 5 & 11)
    uint256 public totalBondedCollateral;

    struct Validator {
        uint256 bondedStake;
        uint256 historicalPerformance;
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
            validators[msg.sender].historicalPerformance = 10000;
            activeValidatorList.push(msg.sender);
        }

        validators[msg.sender].bondedStake += msg.value;
        totalBondedCollateral += msg.value;

        emit ValidatorBonded(msg.sender, msg.value);
    }

    /**
     * @dev Asymmetric Penalization via Anomaly Score (Equation 11)
     * B_new = B_old * (1 - AI_anomaly)
     */
    function slashValidator(address validator, uint256 anomalyBps) external onlyAdmin {
        require(validators[validator].isActive, "Target node is not active");
        require(anomalyBps <= 10000, "Invalid anomaly bounds");

        uint256 currentStake = validators[validator].bondedStake;
        uint256 slashAmount = (currentStake * anomalyBps) / 10000;
        uint256 newStake = currentStake - slashAmount;

        validators[validator].bondedStake = newStake;
        totalBondedCollateral -= slashAmount;

        (bool success, ) = DEAD_ADDRESS.call{value: slashAmount}("");
        require(success, "Burn transfer failed");

        emit ValidatorSlashed(validator, slashAmount, newStake, anomalyBps);

        // Immediate Ejection when anomaly crosses tau_Anomaly = 0.65 or collateral exhausts
        if (anomalyBps >= ANOMALY_EJECTION_THRESHOLD || newStake < MIN_COLLATERAL) {
            validators[validator].isActive = false;
            validators[validator].isBlacklisted = true;
            emit ValidatorEjected(validator, "Anomaly threshold (0.65) exceeded or stake exhausted");
        }
    }

    function getValidatorCount() external view returns (uint256) {
        return activeValidatorList.length;
    }
}