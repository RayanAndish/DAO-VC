// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Voting {
    struct Proposal {
        uint id;
        string description;
        uint voteCount;
    }

    mapping(uint => Proposal) public proposals;
    uint public proposalCount;
    mapping(address => mapping(uint => bool)) public votes;

    function createProposal(string memory description) public {
        proposalCount++;
        proposals[proposalCount] = Proposal(proposalCount, description, 0);
    }

    function vote(uint proposalId) public {
        require(!votes[msg.sender][proposalId], "Already voted");
        votes[msg.sender][proposalId] = true;
        proposals[proposalId].voteCount++;
    }

    function getProposal(uint proposalId) public view returns (Proposal memory) {
        return proposals[proposalId];
    }
}
