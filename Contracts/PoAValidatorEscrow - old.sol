// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PoAValidatorEscrow
 * @dev Production-Grade Validator Collateral Escrow, AI-Attested Slashing,
 *      O(1) Swap-and-Pop Set Management, and Timelocked Stake Unbonding.
 */
contract PoAValidatorEscrow {
    address public governanceAdmin;
    address payable public constant DEAD_ADDRESS = payable(0x000000000000000000000000000000000000dEaD);

    uint256 public constant MIN_COLLATERAL = 10 ether; // Protocol Collateral Floor
    uint256 public constant ANOMALY_EJECTION_THRESHOLD = 6500; // 0.65 Anomaly Cutoff in BPS (Eq. 5)
    uint256 public constant UNBONDING_DELAY_BLOCKS = 20; // Timelock for Stake Withdrawal

    uint256 public totalBondedCollateral;
    uint256 public maxBlockDrift = 5000;
    bytes32 public approvedModelHash;

    uint256 public requiredThreshold;
    uint256 public signerCount;
    mapping(address => bool) public isTelemetrySigner;

    struct Validator {
        uint256 bondedStake;
        uint256 historicalPerformance; // in BPS (10000 = 100%)
        uint256 unbondRequestBlock;
        uint256 unbondAmount;
        uint256 activeListIndex;
        bool isActive;
        bool isBlacklisted;
    }

    mapping(address => Validator) public validators;
    address[] public activeValidatorList;
    mapping(address => uint256) public lastValidatorNonce;

    event ValidatorBonded(address indexed validator, uint256 amount);
    event ValidatorSlashed(address indexed validator, uint256 slashedAmount, uint256 remainingStake, uint256 anomalyScore);
    event ValidatorEjected(address indexed validator, string reason);
    event UnbondRequested(address indexed validator, uint256 amount, uint256 releaseBlock);
    event StakeWithdrawn(address indexed validator, uint256 amount);

    modifier onlyAdmin() {
        require(msg.sender == governanceAdmin, "Unauthorized: caller is not admin");
        _;
    }

    constructor(address[] memory _signers, uint256 _threshold, bytes32 _initialModelHash) {
        governanceAdmin = msg.sender;
        signerCount = _signers.length;
        requiredThreshold = _threshold;
        approvedModelHash = _initialModelHash;

        for (uint256 i = 0; i < _signers.length; i++) {
            isTelemetrySigner[_signers[i]] = true;
        }
    }

    /**
     * @dev Deposit collateral to acquire or expand PoA validation rights
     */
    function depositCollateral() external payable {
        require(msg.value > 0, "Zero deposit");
        Validator storage val = validators[msg.sender];
        require(!val.isBlacklisted, "Validator address is blacklisted");

        val.bondedStake += msg.value;
        totalBondedCollateral += msg.value;

        if (!val.isActive && val.bondedStake >= MIN_COLLATERAL) {
            val.isActive = true;
            val.historicalPerformance = 10000; // 100.00% initial reliability
            val.activeListIndex = activeValidatorList.length;
            activeValidatorList.push(msg.sender);
        }

        emit ValidatorBonded(msg.sender, msg.value);
    }

    /**
     * @dev AI-Attested Asymmetric Validator Slashing (Equations 2 & 11)
     * Verified via k-of-M ECDSA telemetry committee signatures
     */
    function slashValidatorWithAttestation(
        address validator,
        uint256 anomalyBps,
        uint256 epoch,
        uint256 nonce,
        bytes32 modelHash,
        bytes[] memory signatures
    ) external onlyAdmin {
        Validator storage val = validators[validator];
        require(val.isActive, "Target node is not active");
        require(anomalyBps > 0 && anomalyBps <= 10000, "Invalid anomaly bounds");
        require(signatures.length >= requiredThreshold, "Insufficient threshold signatures");
        require(nonce > lastValidatorNonce[validator], "Stale or replayed nonce");
        require(block.number >= epoch && block.number - epoch <= maxBlockDrift, "Attestation expired");
        require(modelHash == approvedModelHash, "Model hash mismatch");

        // Verify cryptographically bound evidence digest
        bytes32 messageHash = keccak256(
            abi.encode(address(this), block.chainid, validator, anomalyBps, epoch, nonce, modelHash)
        );
        bytes32 ethSignedMessageHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash)
        );

        address[] memory verifiedSigners = new address[](signatures.length);
        uint256 validCount = 0;

        for (uint256 i = 0; i < signatures.length; i++) {
            address recovered = recoverSigner(ethSignedMessageHash, signatures[i]);
            require(isTelemetrySigner[recovered], "Unauthorized oracle signer");

            for (uint256 j = 0; j < validCount; j++) {
                require(verifiedSigners[j] != recovered, "Duplicate oracle signature");
            }
            verifiedSigners[validCount] = recovered;
            validCount++;
        }

        lastValidatorNonce[validator] = nonce;

        // Apply Equation 11: B_new = B_old * (1 - Anomaly)
        uint256 currentStake = val.bondedStake;
        uint256 slashAmount = (currentStake * anomalyBps) / 10000;
        uint256 newStake = currentStake - slashAmount;

        val.bondedStake = newStake;
        totalBondedCollateral -= slashAmount;

        // Transfer slashed stake permanently to DEAD_ADDRESS
        (bool burnSuccess, ) = DEAD_ADDRESS.call{value: slashAmount}("");
        require(burnSuccess, "Slashing burn failed");

        // Dynamically degrade historical performance index (A_i)
        if (val.historicalPerformance > (anomalyBps / 2)) {
            val.historicalPerformance -= (anomalyBps / 2);
        } else {
            val.historicalPerformance = 0;
        }

        emit ValidatorSlashed(validator, slashAmount, newStake, anomalyBps);

        // Immediate quarantine and ejection if anomaly crosses tau_Anomaly = 0.65 or collateral exhausts
        if (anomalyBps >= ANOMALY_EJECTION_THRESHOLD || newStake < MIN_COLLATERAL) {
            _removeActiveValidator(validator);
            val.isBlacklisted = true;
            emit ValidatorEjected(validator, "Telemetry anomaly exceeded 0.65 threshold or stake depleted");
        }
    }

    /**
     * @dev O(1) Swap-and-Pop Active Validator Set Removal
     */
    function _removeActiveValidator(address validator) internal {
        Validator storage val = validators[validator];
        if (!val.isActive) return;

        uint256 indexToRemove = val.activeListIndex;
        uint256 lastIndex = activeValidatorList.length - 1;

        if (indexToRemove != lastIndex) {
            address lastValidator = activeValidatorList[lastIndex];
            activeValidatorList[indexToRemove] = lastValidator;
            validators[lastValidator].activeListIndex = indexToRemove;
        }

        activeValidatorList.pop();
        val.isActive = false;
    }

    /**
     * @dev Request unbonding of excess or retiring collateral
     */
    function requestUnbond(uint256 amount) external {
        Validator storage val = validators[msg.sender];
        require(!val.isBlacklisted, "Blacklisted validator cannot unbond normally");
        require(amount > 0 && amount <= val.bondedStake, "Invalid unbond amount");

        val.bondedStake -= amount;
        val.unbondAmount += amount;
        val.unbondRequestBlock = block.number;

        if (val.isActive && val.bondedStake < MIN_COLLATERAL) {
            _removeActiveValidator(msg.sender);
        }

        emit UnbondRequested(msg.sender, amount, block.number + UNBONDING_DELAY_BLOCKS);
    }

    /**
     * @dev Finalize withdrawal after timelock matures
     */
    function withdrawStake() external {
        Validator storage val = validators[msg.sender];
        require(val.unbondAmount > 0, "No pending unbonded collateral");
        require(block.number >= val.unbondRequestBlock + UNBONDING_DELAY_BLOCKS, "Unbonding timelock active");

        uint256 payout = val.unbondAmount;
        val.unbondAmount = 0;
        totalBondedCollateral -= payout;

        (bool success, ) = payable(msg.sender).call{value: payout}("");
        require(success, "Payout transfer failed");

        emit StakeWithdrawn(msg.sender, payout);
    }

    function recoverSigner(bytes32 ethSignedMessageHash, bytes memory sig) internal pure returns (address) {
        require(sig.length == 65, "Malformed signature length");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "Invalid signature 'v'");
        return ecrecover(ethSignedMessageHash, v, r, s);
    }

    function getActiveValidatorCount() external view returns (uint256) {
        return activeValidatorList.length;
    }

    function getValidatorDetails(address val) external view returns (
        uint256 bondedStake,
        uint256 historicalPerformance,
        bool isActive,
        bool isBlacklisted
    ) {
        Validator storage v = validators[val];
        return (v.bondedStake, v.historicalPerformance, v.isActive, v.isBlacklisted);
    }
}