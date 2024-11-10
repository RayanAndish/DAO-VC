// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract HybridConsensus {
    address public admin;
    uint public validatorCount;

    struct Validator {
        address validatorAddress;
        uint256 stake;
        uint256 reputation; // امتیاز اعتبار که براساس مدل هوش مصنوعی بروز می‌شود
        bool isValidator;
    }

    struct Proposal {
        uint id;
        string description;
        uint voteCountYes;
        uint voteCountNo;
        mapping(address => bool) hasVoted;
    }

    mapping(address => Validator) public validators;
    mapping(address => address) public delegations;
    mapping(uint => Proposal) public proposals;
    uint public proposalCount;
    address[] public validatorList;

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can perform this action");
        _;
    }

    modifier onlyValidator() {
        require(validators[msg.sender].isValidator, "Only validator can perform this action");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    // افزودن یک اعتبارسنج جدید با مکانیزم PoA
    function addValidator(address validatorAddress, uint256 initialStake) external onlyAdmin {
        require(!validators[validatorAddress].isValidator, "Validator already exists");
        validators[validatorAddress] = Validator(validatorAddress, initialStake, 0, true);
        validatorList.push(validatorAddress);
        validatorCount++;
    }

    // حذف اعتبارسنج
    function removeValidator(address validatorAddress) external onlyAdmin {
        require(validators[validatorAddress].isValidator, "Validator not found");
        validators[validatorAddress].isValidator = false;
        validatorCount--;
    }

    // ایجاد پروپوزال جدید بدون تخصیص مستقیم
    function createProposal(string memory description) external onlyAdmin {
        proposalCount++;
        Proposal storage newProposal = proposals[proposalCount];
        newProposal.id = proposalCount;
        newProposal.description = description;
        newProposal.voteCountYes = 0;
        newProposal.voteCountNo = 0;
    }

    // تابع رأی‌گیری توسط اعتبارسنج‌ها
    function voteProposal(uint proposalId, bool support) external onlyValidator {
        Proposal storage proposal = proposals[proposalId];
        require(!proposal.hasVoted[msg.sender], "Validator has already voted on this proposal");

        if (support) {
            proposal.voteCountYes++;
        } else {
            proposal.voteCountNo++;
        }

        proposal.hasVoted[msg.sender] = true;
    }

    // تابع بررسی نتیجه رأی‌گیری
    function getProposalResult(uint proposalId) external view returns (string memory description, uint voteCountYes, uint voteCountNo) {
        Proposal storage proposal = proposals[proposalId];
        return (proposal.description, proposal.voteCountYes, proposal.voteCountNo);
    }

    // تابع بررسی وضعیت اعتبارسنج بودن یک حساب
    function isValidator(address account) public view returns (bool) {
        return validators[account].isValidator;
    }

    // دریافت لیست اعتبارسنج‌ها
    function getValidators() public view returns (address[] memory) {
        return validatorList;
    }
}
