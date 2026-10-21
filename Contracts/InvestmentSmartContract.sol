// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title InvestmentSmartContract
 * @dev Threshold ECDSA Attestation, Individual Meritocratic Voting & Macro-Treasury Allocation
 * Strictly implements Bayesian Odds of Success Ratio: Odds(p) = (1 - R(p)) / R(p)
 */
contract InvestmentSmartContract {
    uint256 public constant SCALE = 1e18;
    uint256 public constant TREASURY_POOL = 1_000_000 * 1e18; // $1,000,000 USD (18 decimals)
    uint256 public constant ALPHA_BPS = 4000; // 0.40 Capital Weight
    uint256 public constant BETA_BPS = 6000;  // 0.60 Participation Weight

    address public admin;
    uint256 public votingEpoch;
    uint256 public totalActiveTokens;
    uint256 public totalParticipationScoreSum;
    uint256 public totalVotesCastCount;

    struct Proposal {
        string proposalId;
        uint256 rawTokenVotes;
        uint256 rawParticipationSum;
        uint256 compositeWeight; // V(p)
        uint256 riskScore;      // R(p) scaled 1e18
        bool isAttested;
        uint256 targetAllocationUSD;
        uint256 totalReleasedUSD;
        bool exists;
    }

    mapping(string => Proposal) public proposals;
    string[] public proposalRegistry;

    mapping(address => bool) public isTelemetrySigner;
    uint256 public signerCount;
    uint256 public requiredThreshold; // k-of-M

    event VoteCast(address indexed voter, string proposalId, uint256 tokens, uint256 pScore, uint256 voteIndex);
    event AttestationVerified(string proposalId, uint256 riskScore, uint256 validSignaturesCount);
    event TreasuryAllocated(string proposalId, uint256 allocationAmountUSD, uint256 traditionalAllocationUSD);
    event TrancheDisbursed(string proposalId, uint256 trancheIndex, uint256 amountReleasedUSD);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Caller is not admin");
        _;
    }

    constructor(address[] memory _signers, uint256 _threshold) {
        admin = msg.sender;
        signerCount = _signers.length;
        requiredThreshold = _threshold;

        for (uint256 i = 0; i < _signers.length; i++) {
            isTelemetrySigner[_signers[i]] = true;
        }
    }

    function registerProposal(string memory pid) external onlyAdmin {
        if (!proposals[pid].exists) {
            proposals[pid].proposalId = pid;
            proposals[pid].exists = true;
            proposalRegistry.push(pid);
        }
    }

    function initVotingEpoch() external onlyAdmin {
        totalActiveTokens = 0;
        totalParticipationScoreSum = 0;
        totalVotesCastCount = 0;
        votingEpoch++;
    }

    /**
     * @dev Individual On-Chain Vote Casting
     */
    function castVote(
        string memory pid,
        uint256 tokens,
        uint256 pScore
    ) external {
        require(proposals[pid].exists, "Proposal not registered");

        proposals[pid].rawTokenVotes += tokens;
        proposals[pid].rawParticipationSum += pScore;

        totalActiveTokens += tokens;
        totalParticipationScoreSum += pScore;
        totalVotesCastCount++;

        emit VoteCast(msg.sender, pid, tokens, pScore, totalVotesCastCount);
    }

    /**
     * @dev Reconciles on-chain composite weight V(p) strictly via Eq. 4b
     */
    function finalizeVotingTally() public onlyAdmin {
        require(totalActiveTokens > 0 && totalParticipationScoreSum > 0, "No votes cast");

        for (uint256 i = 0; i < proposalRegistry.length; i++) {
            string memory pid = proposalRegistry[i];
            uint256 tokens = proposals[pid].rawTokenVotes;
            uint256 pScoreSum = proposals[pid].rawParticipationSum;

            uint256 tokenPart = (ALPHA_BPS * tokens) / 10000;
            uint256 popPart = (BETA_BPS * totalActiveTokens * pScoreSum) / (10000 * totalParticipationScoreSum);

            proposals[pid].compositeWeight = tokenPart + popPart;
        }
    }

    function verifyAttestation(
        string memory pid,
        uint256 riskScore,
        uint256 epoch,
        uint256 nonce,
        string memory modelVersion,
        bytes[] memory signatures
    ) public {
        require(signatures.length >= requiredThreshold, "Insufficient attestation signatures");

        bytes32 messageHash = keccak256(
            abi.encodePacked(pid, riskScore, epoch, nonce, modelVersion)
        );
        bytes32 ethSignedMessageHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash)
        );

        address[] memory verifiedSigners = new address[](signatures.length);
        uint256 validCount = 0;

        for (uint256 i = 0; i < signatures.length; i++) {
            address recovered = recoverSigner(ethSignedMessageHash, signatures[i]);
            require(isTelemetrySigner[recovered], "Invalid or unauthorized signer");

            for (uint256 j = 0; j < validCount; j++) {
                require(verifiedSigners[j] != recovered, "Duplicate signature detected");
            }
            verifiedSigners[validCount] = recovered;
            validCount++;
        }

        proposals[pid].riskScore = riskScore;
        proposals[pid].isAttested = true;

        emit AttestationVerified(pid, riskScore, validCount);
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
        if (v < 27) {
            v += 27;
        }
        require(v == 27 || v == 28, "Invalid signature 'v' value");
        return ecrecover(ethSignedMessageHash, v, r, s);
    }

    /**
     * @dev Deterministic Macro Treasury Allocation based on pure Bayesian Odds Ratio (Eq. 8)
     * Numerator = V(p) * ((1 - R_p) / R_p)
     */
    function executeMacroTreasuryAllocation() external onlyAdmin {
        uint256 n = proposalRegistry.length;
        uint256[] memory numerators = new uint256[](n);
        uint256 totalNumeratorSum = 0;

        for (uint256 i = 0; i < n; i++) {
            string memory pid = proposalRegistry[i];
            require(proposals[pid].isAttested, "Proposal not attested");

            uint256 V_p = proposals[pid].compositeWeight;
            uint256 R_p = proposals[pid].riskScore;
            require(R_p > 0 && R_p < SCALE, "Risk score boundary violation");

            // Pure Bayesian Odds Ratio: (1 - R_p) / R_p
            uint256 oddsRatio = ((SCALE - R_p) * SCALE) / R_p;
            uint256 num = (V_p * oddsRatio) / SCALE;

            numerators[i] = num;
            totalNumeratorSum += num;
        }

        require(totalNumeratorSum > 0, "Zero allocation denominator");

        for (uint256 i = 0; i < n; i++) {
            string memory pid = proposalRegistry[i];
            uint256 allocatedUSD = (TREASURY_POOL * numerators[i]) / totalNumeratorSum;
            proposals[pid].targetAllocationUSD = allocatedUSD;

            uint256 tradAlloc = 0;
            if (totalActiveTokens > 0) {
                tradAlloc = (TREASURY_POOL * proposals[pid].rawTokenVotes) / totalActiveTokens;
            }

            emit TreasuryAllocated(pid, allocatedUSD, tradAlloc);
        }
    }
}