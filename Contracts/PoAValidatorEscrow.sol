// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PoAValidatorEscrow (revised)
 * @notice Bonded collateral with timelocked unbonding (E1, E6) and k-of-M attested
 *         slashing (E2). Interface matches 1_deploy_and_run_onchain.py.
 *         E3: zero anomaly rejected. E4: O(1) swap-and-pop ejection. E5: performance
 *         field removed (it was never updated). E7: deployed and exercised by the script.
 */
contract PoAValidatorEscrow {
    address payable public constant DEAD_ADDRESS = payable(0x000000000000000000000000000000000000dEaD);
    uint256 public constant MIN_COLLATERAL = 1 ether;          // script bonds 10 ETH per validator
    uint256 public constant UNBONDING_DELAY_BLOCKS = 20;
    uint256 public constant EJECTION_BPS = 6500;               // tau_Anomaly = 0.65
    uint256 public constant MAX_ATTESTATION_DRIFT = 5000;
    uint256 public constant SECP256K1N_HALF =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    uint256 public immutable threshold;
    uint256 public immutable signerCount;
    bytes32 public immutable approvedModelHash;
    mapping(address => bool) public isCommitteeSigner;

    struct Validator {
        uint256 bondedStake;          // includes pendingUnbond
        uint256 pendingUnbond;        // always <= bondedStake
        uint256 unbondRequestBlock;
        uint256 lastNonce;
        uint256 activeIndexPlusOne;   // 0 = not in active list
        bool isActive;
        bool isBlacklisted;
    }

    mapping(address => Validator) public validators;
    address[] public activeValidatorList;
    uint256 public totalBondedCollateral;

    event ValidatorBonded(address indexed validator, uint256 amount);
    event UnbondRequested(address indexed validator, uint256 amount, uint256 requestBlock);
    event StakeWithdrawn(address indexed validator, uint256 amount);
    event ValidatorSlashed(address indexed validator, uint256 slashedAmount, uint256 remainingStake, uint256 anomalyBps);
    event ValidatorEjected(address indexed validator, string reason);

    constructor(address[] memory _signers, uint256 _threshold, bytes32 _modelHash) {
        require(_threshold > 0 && _threshold <= _signers.length, "Bad threshold");
        threshold = _threshold;
        signerCount = _signers.length;
        approvedModelHash = _modelHash;
        for (uint256 i = 0; i < _signers.length; i++) {
            require(_signers[i] != address(0), "Zero signer");
            isCommitteeSigner[_signers[i]] = true;
        }
    }

    function depositCollateral() external payable {
        Validator storage v = validators[msg.sender];
        require(!v.isBlacklisted, "Validator is blacklisted");
        require(v.bondedStake + msg.value >= MIN_COLLATERAL, "Below minimum collateral");

        if (!v.isActive) {
            v.isActive = true;
            activeValidatorList.push(msg.sender);
            v.activeIndexPlusOne = activeValidatorList.length;
        }
        v.bondedStake += msg.value;
        totalBondedCollateral += msg.value;
        emit ValidatorBonded(msg.sender, msg.value);
    }

    /// @notice Starts the unbonding timer. Stake stays slashable until withdrawn.
    function requestUnbond(uint256 amount) external {
        Validator storage v = validators[msg.sender];
        require(v.isActive, "Not active");
        require(v.pendingUnbond == 0, "Unbond already pending");
        require(amount > 0 && amount <= v.bondedStake, "Bad amount");
        require(v.bondedStake - amount >= MIN_COLLATERAL, "Would fall below minimum collateral");

        v.pendingUnbond = amount;
        v.unbondRequestBlock = block.number;
        emit UnbondRequested(msg.sender, amount, block.number);
    }

    function withdrawStake() external {
        Validator storage v = validators[msg.sender];
        uint256 amount = v.pendingUnbond;
        require(amount > 0, "Nothing pending");
        require(block.number >= v.unbondRequestBlock + UNBONDING_DELAY_BLOCKS, "Unbonding in progress");

        v.pendingUnbond = 0;
        v.bondedStake -= amount;
        totalBondedCollateral -= amount;

        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "Withdrawal transfer failed");
        emit StakeWithdrawn(msg.sender, amount);
    }

    /**
     * @notice Slashes a validator when a k-of-M committee attests to anomaly B(u).
     *         Digest order matches the Python script:
     *         (contract, chainId, validator, anomalyBps, epoch, nonce, modelHash).
     */
    function slashValidatorWithAttestation(
        address validator,
        uint256 anomalyBps,
        uint256 epoch,
        uint256 nonce,
        bytes32 modelHash,
        bytes[] memory signatures
    ) external {
        Validator storage v = validators[validator];
        require(v.isActive, "Target node is not active");
        require(anomalyBps > 0 && anomalyBps <= 10000, "Invalid anomaly bounds");
        require(nonce > v.lastNonce, "Stale nonce");
        require(modelHash == approvedModelHash, "Model hash mismatch");
        require(block.number >= epoch && block.number - epoch <= MAX_ATTESTATION_DRIFT, "Attestation expired");
        require(signatures.length >= threshold, "Insufficient signatures");

        bytes32 digest = keccak256(
            abi.encodePacked(address(this), block.chainid, validator, anomalyBps, epoch, nonce, modelHash)
        );
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        _verifySignatures(ethHash, signatures);

        v.lastNonce = nonce;

        uint256 slashAmount = (v.bondedStake * anomalyBps) / 10000;
        v.bondedStake -= slashAmount;
        if (v.pendingUnbond > v.bondedStake) {
            v.pendingUnbond = v.bondedStake;   // a pending unbond cannot escape the slash
        }
        totalBondedCollateral -= slashAmount;

        (bool burned, ) = DEAD_ADDRESS.call{value: slashAmount}("");
        require(burned, "Burn transfer failed");
        emit ValidatorSlashed(validator, slashAmount, v.bondedStake, anomalyBps);

        if (anomalyBps >= EJECTION_BPS || v.bondedStake < MIN_COLLATERAL) {
            _eject(validator, "Anomaly threshold exceeded or stake exhausted");
        }
    }

    function _verifySignatures(bytes32 ethHash, bytes[] memory signatures) internal view {
        address[] memory seen = new address[](signatures.length);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recoverSigner(ethHash, signatures[i]);
            require(isCommitteeSigner[signer], "Unauthorized committee signer");
            for (uint256 j = 0; j < i; j++) {
                require(seen[j] != signer, "Duplicate signature");
            }
            seen[i] = signer;
        }
    }

    function _recoverSigner(bytes32 hash, bytes memory sig) internal pure returns (address) {
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
        require(uint256(s) <= SECP256K1N_HALF, "Malleable signature");
        address signer = ecrecover(hash, v, r, s);
        require(signer != address(0), "Invalid signature");
        return signer;
    }

    /// @dev O(1) swap-and-pop removal from the active set.
    function _eject(address who, string memory reason) internal {
        Validator storage v = validators[who];
        uint256 idx = v.activeIndexPlusOne - 1;
        uint256 last = activeValidatorList.length - 1;
        if (idx != last) {
            address moved = activeValidatorList[last];
            activeValidatorList[idx] = moved;
            validators[moved].activeIndexPlusOne = idx + 1;
        }
        activeValidatorList.pop();
        v.activeIndexPlusOne = 0;
        v.isActive = false;
        v.isBlacklisted = true;
        emit ValidatorEjected(who, reason);
    }

    function getActiveValidatorCount() external view returns (uint256) {
        return activeValidatorList.length;
    }

    /// @dev Returns bondedStake, pendingUnbond, isActive, isBlacklisted (indices 2 and 3 are used by the script)
    function getValidatorDetails(address who)
        external
        view
        returns (uint256 bondedStake, uint256 pendingUnbond, bool isActive, bool isBlacklisted)
    {
        Validator storage v = validators[who];
        return (v.bondedStake, v.pendingUnbond, v.isActive, v.isBlacklisted);
    }
}
