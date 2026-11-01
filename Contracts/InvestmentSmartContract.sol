// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title InvestmentSmartContract
 * @dev Secure Threshold ECDSA Attestation, On-Chain Voter Registry, 
 *      4-Way On-Chain Ablation, and 40% Capped Bayesian Allocation
 */
contract InvestmentSmartContract {
    uint256 public constant SCALE = 1e18;
    uint256 public constant TREASURY_POOL = 1_000_000 * 1e18; // $1,000,000 USD
    uint256 public constant ALPHA_BPS = 4000; // 0.40 Capital Weight
    uint256 public constant BETA_BPS = 6000;  // 0.60 Participation Weight

    // Institutional VC Portfolio Diversification Cap: 40% Max Exposure per Proposal
    uint256 public constant MAX_CAP_BPS = 4000; // 40.00%
    uint256 public constant MAX_PROPOSAL_ALLOCATION = (TREASURY_POOL * MAX_CAP_BPS) / 10000; // $400,000 USD

    address public admin;
    uint256 public votingEpoch;
    uint256 public totalActiveTokens;
    uint256 public totalParticipationScoreSum;
    uint256 public totalVotesCastCount;

    bool public votingOpen;
    uint256 public maxBlockDrift = 5000;
    bytes32 public approvedModelHash;

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

    struct VoterProfile {
        uint256 tokenBalance;
        uint256 participationScore;
        bool isRegistered;
    }

    mapping(string => Proposal) public proposals;
    string[] public proposalRegistry;

    mapping(address => VoterProfile) public voterRegistry;
    mapping(string => mapping(address => bool)) public hasVoted;
    mapping(string => uint256) public lastVerifiedNonce;

    mapping(address => bool) public isTelemetrySigner;
    uint256 public signerCount;
    uint256 public requiredThreshold;

    event VoterRegistered(address indexed voter, uint256 tokens, uint256 pScore);
    event VoteCast(address indexed voter, string proposalId, uint256 tokens, uint256 pScore, uint256 voteIndex);
    event AttestationVerified(string proposalId, uint256 riskScore, uint256 nonce, uint256 validSignaturesCount);
    event TreasuryAllocated(string proposalId, uint256 allocationAmountUSD, uint256 traditionalAllocationUSD);
    event AblationExecuted(uint8 indexed variant, string proposalId, uint256 allocationUSD);
    event TrancheDisbursed(string proposalId, uint256 trancheIndex, uint256 amountReleasedUSD);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Caller is not admin");
        _;
    }

    constructor(address[] memory _signers, uint256 _threshold, bytes32 _initialModelHash) {
        admin = msg.sender;
        signerCount = _signers.length;
        requiredThreshold = _threshold;
        approvedModelHash = _initialModelHash;

        for (uint256 i = 0; i < _signers.length; i++) {
            isTelemetrySigner[_signers[i]] = true;
        }
    }

    function setVotingState(bool _isOpen) external onlyAdmin {
        votingOpen = _isOpen;
    }

    function registerProposal(string memory pid) external onlyAdmin {
        if (!proposals[pid].exists) {
            proposals[pid].proposalId = pid;
            proposals[pid].exists = true;
            proposalRegistry.push(pid);
        }
    }

    function initVotingEpoch(uint256 _epoch) external onlyAdmin {
        votingEpoch = _epoch;
        votingOpen = true;
    }

    function registerVoterProfiles(
        address[] calldata voters,
        uint256[] calldata tokens,
        uint256[] calldata pScores
    ) external onlyAdmin {
        require(voters.length == tokens.length && tokens.length == pScores.length, "Array mismatch");
        for (uint256 i = 0; i < voters.length; i++) {
            voterRegistry[voters[i]] = VoterProfile({
                tokenBalance: tokens[i],
                participationScore: pScores[i],
                isRegistered: true
            });
            emit VoterRegistered(voters[i], tokens[i], pScores[i]);
        }
    }

    function castVote(string memory pid) external {
        require(votingOpen, "Voting window closed");
        require(proposals[pid].exists, "Proposal not registered");
        require(voterRegistry[msg.sender].isRegistered, "Caller not registered");
        require(!hasVoted[pid][msg.sender], "Double voting prohibited");

        hasVoted[pid][msg.sender] = true;

        uint256 tokens = voterRegistry[msg.sender].tokenBalance;
        uint256 pScore = voterRegistry[msg.sender].participationScore;

        proposals[pid].rawTokenVotes += tokens;
        proposals[pid].rawParticipationSum += pScore;

        totalActiveTokens += tokens;
        totalParticipationScoreSum += pScore;
        totalVotesCastCount++;

        emit VoteCast(msg.sender, pid, tokens, pScore, totalVotesCastCount);
    }

    function finalizeVotingTally() external onlyAdmin {
        require(totalActiveTokens > 0 && totalParticipationScoreSum > 0, "No votes cast");
        votingOpen = false;

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
        bytes32 modelHash,
        bytes[] memory signatures
    ) public {
        require(proposals[pid].exists, "Proposal not registered");
        require(signatures.length >= requiredThreshold, "Insufficient signatures");
        require(nonce > lastVerifiedNonce[pid], "Stale nonce");
        require(block.number >= epoch && block.number - epoch <= maxBlockDrift, "Attestation expired");
        require(modelHash == approvedModelHash, "Model hash mismatch");

        bytes32 messageHash = keccak256(
            abi.encodePacked(pid, riskScore, epoch, nonce, modelHash)
        );
        bytes32 ethSignedMessageHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash)
        );

        address[] memory verifiedSigners = new address[](signatures.length);
        uint256 validCount = 0;

        for (uint256 i = 0; i < signatures.length; i++) {
            address recovered = recoverSigner(ethSignedMessageHash, signatures[i]);
            require(isTelemetrySigner[recovered], "Unauthorized signer");

            for (uint256 j = 0; j < validCount; j++) {
                require(verifiedSigners[j] != recovered, "Duplicate signature");
            }
            verifiedSigners[validCount] = recovered;
            validCount++;
        }

        lastVerifiedNonce[pid] = nonce;
        proposals[pid].riskScore = riskScore;
        proposals[pid].isAttested = true;

        emit AttestationVerified(pid, riskScore, nonce, validCount);
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

    /**
     * @dev Core Water-Filling Algorithm executed purely ON-CHAIN
     */
    function _applyWaterFilling(uint256[] memory weights) internal pure returns (uint256[] memory allocations) {
        uint256 n = weights.length;
        allocations = new uint256[](n);
        bool[] memory isCapped = new bool[](n);
        uint256 remainingTreasury = TREASURY_POOL;

        for (uint256 round = 0; round < n; round++) {
            uint256 uncappedWeightSum = 0;
            for (uint256 i = 0; i < n; i++) {
                if (!isCapped[i]) {
                    uncappedWeightSum += weights[i];
                }
            }

            if (uncappedWeightSum == 0) break;

            bool capExceeded = false;
            for (uint256 i = 0; i < n; i++) {
                if (!isCapped[i]) {
                    uint256 candidate = (remainingTreasury * weights[i]) / uncappedWeightSum;
                    if (candidate > MAX_PROPOSAL_ALLOCATION) {
                        allocations[i] = MAX_PROPOSAL_ALLOCATION;
                        isCapped[i] = true;
                        remainingTreasury -= MAX_PROPOSAL_ALLOCATION;
                        capExceeded = true;
                        break;
                    }
                }
            }

            if (!capExceeded) {
                for (uint256 i = 0; i < n; i++) {
                    if (!isCapped[i]) {
                        allocations[i] = (remainingTreasury * weights[i]) / uncappedWeightSum;
                    }
                }
                break;
            }
        }
    }

    /**
     * @dev 4-Way Ablation Allocations Executed 100% On-Chain
     * Variant 1: Pure Token Voting
     * Variant 2: Token + PoP (No AI Risk Gate)
     * Variant 3: Token + AI Risk Gate (No PoP)
     * Variant 4: Full AIPoX Architecture (PoP + AI Gate + 40% Cap)
     */
    function executeAblationAllocation(uint8 variant) public onlyAdmin returns (uint256[] memory allocations) {
        uint256 n = proposalRegistry.length;
        uint256[] memory weights = new uint256[](n);

        if (variant == 1) {
            // Variant 1: Token Only
            allocations = new uint256[](n);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                allocations[i] = (TREASURY_POOL * proposals[pid].rawTokenVotes) / totalActiveTokens;
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        } else if (variant == 2) {
            // Variant 2: Token + PoP
            uint256 sumComposite = 0;
            for (uint256 i = 0; i < n; i++) {
                sumComposite += proposals[proposalRegistry[i]].compositeWeight;
            }
            allocations = new uint256[](n);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                allocations[i] = (TREASURY_POOL * proposals[pid].compositeWeight) / sumComposite;
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        } else if (variant == 3) {
            // Variant 3: Token + AI Gate
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                require(proposals[pid].isAttested, "Proposal not attested");
                uint256 R_p = proposals[pid].riskScore;
                uint256 oddsRatio = ((SCALE - R_p) * SCALE) / R_p;
                weights[i] = (proposals[pid].rawTokenVotes * oddsRatio) / SCALE;
            }
            allocations = _applyWaterFilling(weights);
            for (uint256 i = 0; i < n; i++) {
                emit AblationExecuted(variant, proposalRegistry[i], allocations[i]);
            }
            return allocations;
        } else if (variant == 4) {
            // Variant 4: Full AIPoX
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                require(proposals[pid].isAttested, "Proposal not attested");
                uint256 V_p = proposals[pid].compositeWeight;
                uint256 R_p = proposals[pid].riskScore;
                uint256 oddsRatio = ((SCALE - R_p) * SCALE) / R_p;
                weights[i] = (V_p * oddsRatio) / SCALE;
            }
            allocations = _applyWaterFilling(weights);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                proposals[pid].targetAllocationUSD = allocations[i];
                uint256 tradAlloc = (TREASURY_POOL * proposals[pid].rawTokenVotes) / totalActiveTokens;
                emit TreasuryAllocated(pid, allocations[i], tradAlloc);
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        } else {
            revert("Invalid ablation variant");
        }
    }

    function executeMacroTreasuryAllocation() external onlyAdmin returns (uint256[] memory) {
    return executeAblationAllocation(4);
    }

    function disburseMilestoneTranche(
        string memory pid,
        uint256 trancheIndex,
        uint256 muBps,
        uint256 progressBps
    ) external onlyAdmin {
        Proposal storage prop = proposals[pid];
        require(prop.targetAllocationUSD > 0, "No allocation assigned");
        require(muBps <= 10000 && progressBps <= 10000, "Percentage overflow");

        uint256 plannedTranche = (prop.targetAllocationUSD * muBps) / 10000;
        uint256 releasedAmount = (plannedTranche * progressBps) / 10000;

        prop.totalReleasedUSD += releasedAmount;
        emit TrancheDisbursed(pid, trancheIndex, releasedAmount);
    }
}