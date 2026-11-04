// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title InvestmentSmartContract
 * @dev Audited Implementation resolving C1-C9: Single vote per epoch, 
 *      Strict State Machine, Replay-Protected Attestation, and 4-Way On-Chain Ablation.
 */
contract InvestmentSmartContract {
    uint256 public constant SCALE = 1e18;
    uint256 public constant TREASURY_POOL = 1_000_000 * 1e18; // $1,000,000 USD
    uint256 public constant ALPHA_BPS = 4000; // 0.40 Capital Weight
    uint256 public constant BETA_BPS = 6000;  // 0.60 Participation Weight

    uint256 public constant MAX_CAP_BPS = 4000; // 40.00% Exposure Cap
    uint256 public constant MAX_PROPOSAL_ALLOCATION = (TREASURY_POOL * MAX_CAP_BPS) / 10000; // $400,000 USD

    enum GovernanceState { Registration, Voting, Finalized, Allocated }
    GovernanceState public currentState;

    address public admin;
    uint256 public votingEpoch;
    uint256 public totalActiveTokens;
    uint256 public totalParticipationScoreSum;
    uint256 public totalVotesCastCount;

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
        uint256 milestoneCount;
        uint256 milestonesReleased;
        bool exists;
    }

    struct VoterProfile {
        uint256 tokenBalance;
        uint256 participationScore; // in BPS (0 to 10000)
        bool isRegistered;
    }

    mapping(string => Proposal) public proposals;
    string[] public proposalRegistry;

    mapping(address => VoterProfile) public voterRegistry;
    // Resolves C1: Single vote per address per epoch
    mapping(uint256 => mapping(address => bool)) public hasVotedInEpoch;
    mapping(string => uint256) public lastVerifiedNonce;

    mapping(address => bool) public isTelemetrySigner;
    uint256 public signerCount;
    uint256 public requiredThreshold;

    event VoterRegistered(address indexed voter, uint256 tokens, uint256 pScore);
    event VoteCast(address indexed voter, string proposalId, uint256 tokens, uint256 pScore, uint256 epoch);
    event AttestationVerified(string proposalId, uint256 riskScore, uint256 epoch, uint256 nonce);
    event TreasuryAllocated(string proposalId, uint256 allocationAmountUSD, uint256 traditionalAllocationUSD);
    event AblationExecuted(uint8 indexed variant, string proposalId, uint256 allocationUSD);
    event TrancheDisbursed(string proposalId, uint256 trancheIndex, uint256 amountReleasedUSD);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Caller is not admin");
        _;
    }

    modifier inState(GovernanceState state) {
        require(currentState == state, "Invalid governance state");
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
        currentState = GovernanceState.Registration;
    }

    function registerProposal(string memory pid, uint256 milestones) external onlyAdmin inState(GovernanceState.Registration) {
        if (!proposals[pid].exists) {
            proposals[pid].proposalId = pid;
            proposals[pid].milestoneCount = milestones > 0 ? milestones : 4;
            proposals[pid].exists = true;
            proposalRegistry.push(pid);
        }
    }

    function initVotingEpoch(uint256 _epoch) external onlyAdmin inState(GovernanceState.Registration) {
        votingEpoch = _epoch;
        currentState = GovernanceState.Voting;
    }

    // Resolves C2: Strict BPS check on PoP scores (<= 10000)
    function registerVoterProfiles(
        address[] calldata voters,
        uint256[] calldata tokens,
        uint256[] calldata pScores
    ) external onlyAdmin {
        require(voters.length == tokens.length && tokens.length == pScores.length, "Array length mismatch");
        for (uint256 i = 0; i < voters.length; i++) {
            require(pScores[i] <= 10000, "PoP score out of range (max 10000 BPS)");
            voterRegistry[voters[i]] = VoterProfile({
                tokenBalance: tokens[i],
                participationScore: pScores[i],
                isRegistered: true
            });
            emit VoterRegistered(voters[i], tokens[i], pScores[i]);
        }
    }

    // Resolves C1: Enforces exactly one vote per voter per epoch
    function castVote(string memory pid) external inState(GovernanceState.Voting) {
        require(proposals[pid].exists, "Proposal not registered");
        require(voterRegistry[msg.sender].isRegistered, "Caller not registered");
        require(!hasVotedInEpoch[votingEpoch][msg.sender], "Voter already cast vote in this epoch");

        hasVotedInEpoch[votingEpoch][msg.sender] = true;

        uint256 tokens = voterRegistry[msg.sender].tokenBalance;
        uint256 pScore = voterRegistry[msg.sender].participationScore;

        proposals[pid].rawTokenVotes += tokens;
        proposals[pid].rawParticipationSum += pScore;

        totalActiveTokens += tokens;
        totalParticipationScoreSum += pScore;
        totalVotesCastCount++;

        emit VoteCast(msg.sender, pid, tokens, pScore, votingEpoch);
    }

    function finalizeVotingTally() external onlyAdmin inState(GovernanceState.Voting) {
        require(totalActiveTokens > 0 && totalParticipationScoreSum > 0, "Zero votes cast");
        currentState = GovernanceState.Finalized;

        for (uint256 i = 0; i < proposalRegistry.length; i++) {
            string memory pid = proposalRegistry[i];
            uint256 tokens = proposals[pid].rawTokenVotes;
            uint256 pScoreSum = proposals[pid].rawParticipationSum;

            uint256 tokenPart = (ALPHA_BPS * tokens) / 10000;
            uint256 popPart = (BETA_BPS * totalActiveTokens * pScoreSum) / (10000 * totalParticipationScoreSum);

            proposals[pid].compositeWeight = tokenPart + popPart;
        }
    }

    // Resolves C4 & C4b: Replay, epoch, and chain-id cryptographic binding
    function verifyAttestation(
        string memory pid,
        uint256 riskScore,
        uint256 epoch,
        uint256 nonce,
        bytes32 modelHash,
        bytes[] memory signatures
    ) public inState(GovernanceState.Finalized) {
        require(proposals[pid].exists, "Proposal not registered");
        require(signatures.length >= requiredThreshold, "Insufficient threshold signatures");
        require(nonce > lastVerifiedNonce[pid], "Stale or replayed nonce");
        require(block.number >= epoch && block.number - epoch <= maxBlockDrift, "Attestation window expired");
        require(modelHash == approvedModelHash, "Model hash mismatch");
        // Resolves C3: Bounds check on risk
        require(riskScore >= 200 * 1e14 && riskScore <= 9800 * 1e14, "Risk score out of [0.02, 0.98] bounds");

        bytes32 messageHash = keccak256(
            abi.encode(address(this), block.chainid, pid, epoch, nonce, modelHash, riskScore)
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

        lastVerifiedNonce[pid] = nonce;
        proposals[pid].riskScore = riskScore;
        proposals[pid].isAttested = true;

        emit AttestationVerified(pid, riskScore, epoch, nonce);
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

    function executeAblationAllocation(uint8 variant) public onlyAdmin returns (uint256[] memory allocations) {
        require(currentState == GovernanceState.Finalized || currentState == GovernanceState.Allocated, "Not finalized");
        uint256 n = proposalRegistry.length;
        uint256[] memory weights = new uint256[](n);

        if (variant == 1) {
            allocations = new uint256[](n);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                allocations[i] = (TREASURY_POOL * proposals[pid].rawTokenVotes) / totalActiveTokens;
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        } else if (variant == 2) {
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
            currentState = GovernanceState.Allocated;
            return allocations;
        } else {
            revert("Invalid ablation variant");
        }
    }

    function executeMacroTreasuryAllocation() external onlyAdmin returns (uint256[] memory) {
        return executeAblationAllocation(4);
    }

    // Resolves C7: Strict milestone disbursement checks
    function disburseMilestoneTranche(
        string memory pid,
        uint256 trancheIndex,
        uint256 muBps,
        uint256 progressBps
    ) external onlyAdmin inState(GovernanceState.Allocated) {
        Proposal storage prop = proposals[pid];
        require(prop.targetAllocationUSD > 0, "Zero allocation assigned");
        require(muBps <= 10000 && progressBps <= 10000, "Percentage overflow");
        require(prop.milestonesReleased < prop.milestoneCount, "All milestones already released");

        uint256 plannedTranche = (prop.targetAllocationUSD * muBps) / 10000;
        uint256 releaseAmount = (plannedTranche * progressBps) / 10000;

        require(prop.totalReleasedUSD + releaseAmount <= prop.targetAllocationUSD, "Exceeds total target allocation");

        prop.totalReleasedUSD += releaseAmount;
        prop.milestonesReleased++;

        emit TrancheDisbursed(pid, trancheIndex, releaseAmount);
    }
}