// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract Voting is Ownable {
    struct Proposal {
        uint id;
        string description;
        uint256 startTime;
        uint256 endTime;
        uint[] voteCounts; // تعداد رأی‌ها برای هر گزینه
        bool finalized;
    }

    uint public proposalCount;
    mapping(uint => Proposal) public proposals;
    mapping(address => mapping(uint => bool)) public hasVoted;

    uint256 public votingFeeRate;
    address public feeCollector;

    IERC20 public governanceToken;

    event ProposalCreated(uint indexed proposalId, string description, uint256 startTime, uint256 endTime);
    event Voted(uint indexed proposalId, address voter, uint option, uint256 voterWeight);
    event ProposalFinalized(uint indexed proposalId, uint winningOption);

    modifier onlyWithinTime(uint proposalId) {
        require(block.timestamp >= proposals[proposalId].startTime, "Voting has not started");
        require(block.timestamp <= proposals[proposalId].endTime, "Voting period has ended");
        _;
    }

    constructor(
        uint256 _votingFeeRate,
        address _feeCollector,
        address _governanceToken
    ) {
        votingFeeRate = _votingFeeRate;
        feeCollector = _feeCollector;
        governanceToken = IERC20(_governanceToken);
    }

    function setFeeCollector(address _feeCollector) external onlyOwner {
        feeCollector = _feeCollector;
    }

    function createProposal(
        string memory description,
        uint256 startTime,
        uint256 endTime,
        uint[] memory options
    ) external onlyOwner {
        require(startTime < endTime, "Invalid time range");

        proposalCount++;
        Proposal storage newProposal = proposals[proposalCount];
        newProposal.id = proposalCount;
        newProposal.description = description;
        newProposal.startTime = startTime;
        newProposal.endTime = endTime;
        newProposal.voteCounts = new uint[](options.length);
        newProposal.finalized = false;

        emit ProposalCreated(proposalCount, description, startTime, endTime);
    }

    function vote(uint proposalId, uint option) external payable onlyWithinTime(proposalId) {
        Proposal storage proposal = proposals[proposalId];
        require(!hasVoted[msg.sender][proposalId], "Already voted");
        require(option < proposal.voteCounts.length, "Invalid option");

        require(msg.value >= votingFeeRate, "Insufficient voting fee");
        payable(feeCollector).transfer(msg.value);

        uint256 voterWeight = governanceToken.balanceOf(msg.sender);
        require(voterWeight > 0, "No voting power");

        hasVoted[msg.sender][proposalId] = true;
        proposal.voteCounts[option] += voterWeight;

        emit Voted(proposalId, msg.sender, option, voterWeight);
    }

    function finalizeProposal(uint proposalId) external onlyOwner {
        Proposal storage proposal = proposals[proposalId];
        require(!proposal.finalized, "Already finalized");
        require(block.timestamp > proposal.endTime, "Voting still active");

        uint256 winningOption;
        uint256 highestVotes;

        for (uint i = 0; i < proposal.voteCounts.length; i++) {
            if (proposal.voteCounts[i] > highestVotes) {
                highestVotes = proposal.voteCounts[i];
                winningOption = i;
            }
        }

        proposal.finalized = true;

        emit ProposalFinalized(proposalId, winningOption);
    }

    function getProposal(uint proposalId)
        public
        view
        returns (
            uint id,
            string memory description,
            uint startTime,
            uint endTime,
            uint[] memory voteCounts,
            bool finalized
        )
    {
        Proposal storage proposal = proposals[proposalId];
        return (
            proposal.id,
            proposal.description,
            proposal.startTime,
            proposal.endTime,
            proposal.voteCounts,
            proposal.finalized
        );
    }

    function isVotingActive(uint proposalId) public view returns (bool) {
        Proposal storage proposal = proposals[proposalId];
        return block.timestamp >= proposal.startTime && block.timestamp <= proposal.endTime;
    }
}