// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title InvestmentSmartContract (revised)
 * @notice One deployment = one voting epoch.
 *         Phase machine: Idle -> Voting -> Finalized -> Allocated (one-way).
 *         Fixes: C1 (one vote per voter per epoch), C2 (PoP bounded to 10000 bps),
 *         C3 (risk bounded to [0.02, 0.98]), C4/C4b (digest bound to address, chainid,
 *         epoch and model hash; epoch must equal votingEpoch), C5 (phase machine),
 *         C6 (unallocated residue recorded), C7 (sequenced, cumulative-capped tranches).
 */
contract InvestmentSmartContract {
    uint256 public constant SCALE = 1e18;
    uint256 public constant TREASURY_POOL = 1_000_000 * 1e18;   // $1,000,000
    uint256 public constant ALPHA_BPS = 4000;                    // 0.40 capital weight
    uint256 public constant BETA_BPS = 6000;                     // 0.60 participation weight
    uint256 public constant MAX_CAP_BPS = 4000;                  // 40% per-proposal cap
    uint256 public constant MAX_PROPOSAL_ALLOCATION = (TREASURY_POOL * MAX_CAP_BPS) / 10000;
    uint256 public constant MIN_RISK = 2e16;                     // R(p) >= 0.02
    uint256 public constant MAX_RISK = 98e16;                    // R(p) <= 0.98
    uint256 public constant MAX_PARTICIPATION_BPS = 10000;
    // secp256k1 n / 2 (EIP-2): rejects malleable high-s signatures
    uint256 public constant SECP256K1N_HALF =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    enum Phase { Idle, Voting, Finalized, Allocated }

    struct Proposal {
        string proposalId;
        uint256 rawTokenVotes;
        uint256 rawParticipationSum;
        uint256 compositeWeight;   // V(p)
        uint256 riskScore;         // R(p), scaled 1e18
        bool isAttested;
        uint256 targetAllocationUSD;
        uint256 totalReleasedUSD;
        bool exists;
    }

    struct VoterProfile {
        uint256 tokenBalance;
        uint256 participationScore; // P in basis points (0..10000)
        bool isRegistered;
    }

    address public immutable admin;
    Phase public phase;
    uint256 public votingEpoch;
    uint256 public totalActiveTokens;
    uint256 public totalParticipationScoreSum;
    uint256 public totalVotesCastCount;
    uint256 public maxBlockDrift = 5000;
    bytes32 public approvedModelHash;
    uint256 public unallocatedTreasury;   // C6: residue after water-filling (USD wei)

    mapping(string => Proposal) public proposals;
    string[] public proposalRegistry;

    mapping(address => VoterProfile) public voterRegistry;
    uint256 public minVoteStake = 0;             // minimum tokens an identity must lock to vote
    mapping(address => uint256) public lockedStake; // tokens locked by a voter in the current epoch
    uint256 public totalLockedStake;

    event StakeLocked(address indexed voter, uint256 amount);
    event StakeReleased(address indexed voter, uint256 amount);
    mapping(uint256 => mapping(address => bool)) public hasVoted;   // C1: keyed by epoch, one vote total
    mapping(string => uint256) public lastVerifiedNonce;
    mapping(string => uint256) public lastTrancheIndex;             // C7
    mapping(string => uint256) public cumulativeMuBps;              // C7

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

    modifier inPhase(Phase p) {
        require(phase == p, "Invalid phase");
        _;
    }

    constructor(address[] memory _signers, uint256 _threshold, bytes32 _initialModelHash) {
        require(_threshold > 0 && _threshold <= _signers.length, "Bad threshold");
        admin = msg.sender;
        signerCount = _signers.length;
        requiredThreshold = _threshold;
        approvedModelHash = _initialModelHash;
        for (uint256 i = 0; i < _signers.length; i++) {
            require(_signers[i] != address(0), "Zero signer");
            isTelemetrySigner[_signers[i]] = true;
        }
    }

    // ------------------------------------------------------------------
    // Registration (Idle only)
    // ------------------------------------------------------------------
    function registerProposal(string memory pid) external onlyAdmin inPhase(Phase.Idle) {
        require(!proposals[pid].exists, "Already registered");
        proposals[pid].proposalId = pid;
        proposals[pid].exists = true;
        proposalRegistry.push(pid);
    }

    function registerVoterProfiles(
        address[] calldata voters,
        uint256[] calldata tokens,
        uint256[] calldata pScores
    ) external onlyAdmin inPhase(Phase.Idle) {
        require(voters.length == tokens.length && tokens.length == pScores.length, "Array mismatch");
        for (uint256 i = 0; i < voters.length; i++) {
            require(tokens[i] > 0, "Zero tokens");
            require(pScores[i] <= MAX_PARTICIPATION_BPS, "PoP out of range");
            voterRegistry[voters[i]] = VoterProfile({
                tokenBalance: tokens[i],
                participationScore: pScores[i],
                isRegistered: true
            });
            emit VoterRegistered(voters[i], tokens[i], pScores[i]);
        }
    }

    // ------------------------------------------------------------------
    // Voting lifecycle
    // ------------------------------------------------------------------
    function initVotingEpoch(uint256 _epoch) external onlyAdmin inPhase(Phase.Idle) {
        votingEpoch = _epoch;
        phase = Phase.Voting;
    }
    
    function setMinVoteStake(uint256 _min) external onlyAdmin {
        require(phase == Phase.Idle, "Cannot change after registration");
        minVoteStake = _min;
    }

    function castVote(string memory pid) external inPhase(Phase.Voting) {
        require(proposals[pid].exists, "Proposal not registered");
        require(voterRegistry[msg.sender].isRegistered, "Caller not registered");
        require(!hasVoted[votingEpoch][msg.sender], "One vote per voter per epoch"); // C1

        uint256 tokens = voterRegistry[msg.sender].tokenBalance;
        require(tokens >= minVoteStake, "Stake below minimum");
        require(lockedStake[msg.sender] == 0, "Stake already locked");

        hasVoted[votingEpoch][msg.sender] = true;
        lockedStake[msg.sender] = tokens;
        totalLockedStake += tokens;
        emit StakeLocked(msg.sender, tokens);

        uint256 pScore = voterRegistry[msg.sender].participationScore;

        proposals[pid].rawTokenVotes += tokens;
        proposals[pid].rawParticipationSum += pScore;

        totalActiveTokens += tokens;
        totalParticipationScoreSum += pScore;
        totalVotesCastCount++;

        emit VoteCast(msg.sender, pid, tokens, pScore, totalVotesCastCount);
    }

    function finalizeVotingTally() external onlyAdmin inPhase(Phase.Voting) {
        require(totalActiveTokens > 0 && totalParticipationScoreSum > 0, "No votes cast");
        phase = Phase.Finalized;

        for (uint256 i = 0; i < proposalRegistry.length; i++) {
            Proposal storage p = proposals[proposalRegistry[i]];
            uint256 tokenPart = (ALPHA_BPS * p.rawTokenVotes) / 10000;
            uint256 popPart = (BETA_BPS * totalActiveTokens * p.rawParticipationSum)
                / (10000 * totalParticipationScoreSum);
            p.compositeWeight = tokenPart + popPart;
        }
    }
    
    function releaseStake() external {
        require(phase != Phase.Voting, "Stake locked until finalisation");
        uint256 amount = lockedStake[msg.sender];
        require(amount > 0, "Nothing locked");
        lockedStake[msg.sender] = 0;
        totalLockedStake -= amount;
        emit StakeReleased(msg.sender, amount);
    }

    // ------------------------------------------------------------------
    // Attestation (Finalized only)
    // ------------------------------------------------------------------
    function verifyAttestation(
        string memory pid,
        uint256 riskScore,
        uint256 epoch,
        uint256 nonce,
        bytes32 modelHash,
        bytes[] memory signatures
    ) public inPhase(Phase.Finalized) {
        Proposal storage p = proposals[pid];
        require(p.exists, "Proposal not registered");
        require(epoch == votingEpoch, "Epoch mismatch");
        require(block.number >= epoch && block.number - epoch <= maxBlockDrift, "Attestation expired");
        require(nonce > lastVerifiedNonce[pid], "Stale nonce");
        require(riskScore >= MIN_RISK && riskScore <= MAX_RISK, "Risk out of bounds");
        require(modelHash == approvedModelHash, "Model hash mismatch");
        require(signatures.length >= requiredThreshold, "Insufficient signatures");

        // Digest order matches the Python deploy script exactly:
        // (contract, chainId, pid, epoch, nonce, modelHash, riskScore)
        bytes32 digest = keccak256(
            abi.encodePacked(address(this), block.chainid, pid, epoch, nonce, modelHash, riskScore)
        );
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));

        address[] memory seen = new address[](signatures.length);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = _recoverSigner(ethHash, signatures[i]);
            require(isTelemetrySigner[signer], "Unauthorized signer");
            for (uint256 j = 0; j < i; j++) {
                require(seen[j] != signer, "Duplicate signature");
            }
            seen[i] = signer;
        }

        lastVerifiedNonce[pid] = nonce;
        p.riskScore = riskScore;
        p.isAttested = true;
        emit AttestationVerified(pid, riskScore, nonce, signatures.length);
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

    // ------------------------------------------------------------------
    // Allocation
    // ------------------------------------------------------------------

    /**
     * @dev Water-filling with a per-proposal cap. Each round caps at most one
     *      proposal and redistributes the rest; the final pass uses floor division,
     *      so the residue is reported by the caller as unallocatedTreasury (C6).
     */
    function _applyWaterFilling(uint256[] memory weights) internal pure returns (uint256[] memory allocations) {
        uint256 n = weights.length;
        allocations = new uint256[](n);
        bool[] memory isCapped = new bool[](n);
        uint256 remaining = TREASURY_POOL;

        for (uint256 round = 0; round < n; round++) {
            uint256 wSum = 0;
            for (uint256 i = 0; i < n; i++) {
                if (!isCapped[i]) wSum += weights[i];
            }
            if (wSum == 0) break;

            bool capped = false;
            for (uint256 i = 0; i < n; i++) {
                if (!isCapped[i] && (remaining * weights[i]) / wSum > MAX_PROPOSAL_ALLOCATION) {
                    allocations[i] = MAX_PROPOSAL_ALLOCATION;
                    isCapped[i] = true;
                    remaining -= MAX_PROPOSAL_ALLOCATION;   // safe: candidate > cap implies remaining > cap
                    capped = true;
                    break;
                }
            }

            if (!capped) {
                for (uint256 i = 0; i < n; i++) {
                    if (!isCapped[i]) allocations[i] = (remaining * weights[i]) / wSum;
                }
                break;
            }
        }
    }

    /**
     * @dev Variant 1: token-only. Variant 2: token + PoP. Variant 3: token + AI gate.
     *      Variant 4: full AIPoX (PoP + AI gate + 40% cap). Variants 3 and 4 use
     *      Bayesian odds (1-R)/R with water-filling.
     */
    function executeAblationAllocation(uint8 variant) public onlyAdmin returns (uint256[] memory allocations) {
        require(phase == Phase.Finalized || phase == Phase.Allocated, "Tally not finalized");
        uint256 n = proposalRegistry.length;

        if (variant == 1) {
            require(totalActiveTokens > 0, "No tokens");
            allocations = new uint256[](n);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                allocations[i] = (TREASURY_POOL * proposals[pid].rawTokenVotes) / totalActiveTokens;
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        }

        if (variant == 2) {
            uint256 sumComposite = 0;
            for (uint256 i = 0; i < n; i++) {
                sumComposite += proposals[proposalRegistry[i]].compositeWeight;
            }
            require(sumComposite > 0, "Zero composite weight");
            allocations = new uint256[](n);
            for (uint256 i = 0; i < n; i++) {
                string memory pid = proposalRegistry[i];
                allocations[i] = (TREASURY_POOL * proposals[pid].compositeWeight) / sumComposite;
                emit AblationExecuted(variant, pid, allocations[i]);
            }
            return allocations;
        }

        require(variant == 3 || variant == 4, "Invalid ablation variant");

        uint256[] memory weights = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            Proposal storage p = proposals[proposalRegistry[i]];
            require(p.isAttested, "Proposal not attested");
            uint256 base = variant == 3 ? p.rawTokenVotes : p.compositeWeight;
            uint256 oddsRatio = ((SCALE - p.riskScore) * SCALE) / p.riskScore;
            weights[i] = (base * oddsRatio) / SCALE;
        }
        allocations = _applyWaterFilling(weights);

        uint256 sum = 0;
        for (uint256 i = 0; i < n; i++) {
            string memory pid = proposalRegistry[i];
            sum += allocations[i];
            emit AblationExecuted(variant, pid, allocations[i]);
            if (variant == 4) {
                Proposal storage p = proposals[pid];
                p.targetAllocationUSD = allocations[i];
                uint256 tradAlloc = (TREASURY_POOL * p.rawTokenVotes) / totalActiveTokens;
                emit TreasuryAllocated(pid, allocations[i], tradAlloc);
            }
        }

        if (variant == 4) {
            unallocatedTreasury = TREASURY_POOL - sum;
            phase = Phase.Allocated;
        }
        return allocations;
    }

    function executeMacroTreasuryAllocation() external onlyAdmin returns (uint256[] memory) {
        return executeAblationAllocation(4);
    }

    /**
     * @dev C7: tranches must be sequential and cumulative mu may not exceed 100%.
     *      Total released can never exceed the assigned allocation.
     */
    function disburseMilestoneTranche(
        string memory pid,
        uint256 trancheIndex,
        uint256 muBps,
        uint256 progressBps
    ) external onlyAdmin {
        Proposal storage p = proposals[pid];
        require(p.isAttested && p.targetAllocationUSD > 0, "No allocation assigned");
        require(trancheIndex == lastTrancheIndex[pid] + 1, "Tranche out of sequence");
        require(muBps > 0 && muBps <= 10000 && progressBps <= 10000, "Percentage out of range");

        cumulativeMuBps[pid] += muBps;
        require(cumulativeMuBps[pid] <= 10000, "Tranches exceed budget");
        lastTrancheIndex[pid] = trancheIndex;

        uint256 planned = (p.targetAllocationUSD * muBps) / 10000;
        uint256 released = (planned * progressBps) / 10000;
        p.totalReleasedUSD += released;
        require(p.totalReleasedUSD <= p.targetAllocationUSD, "Over-disbursement");

        emit TrancheDisbursed(pid, trancheIndex, released);
    }
}
