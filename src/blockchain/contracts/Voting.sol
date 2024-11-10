// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Voting {
    struct Proposal {
        uint id;
        string description;
        uint voteCount;
    }

    address public admin;
    uint public proposalCount;
    mapping(uint => Proposal) public proposals;
    mapping(address => mapping(uint => bool)) public votes;

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can perform this action");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function createProposal(string memory description) public onlyAdmin {
        proposalCount++;
        proposals[proposalCount] = Proposal(proposalCount, description, 0);
    }

    function vote(uint proposalId) public {
        require(!votes[msg.sender][proposalId], "Already voted");
        require(proposals[proposalId].id != 0, "Proposal does not exist");

        votes[msg.sender][proposalId] = true;
        proposals[proposalId].voteCount++;
    }

    function getProposal(uint proposalId) public view returns (Proposal memory) {
        return proposals[proposalId];
    }
}
