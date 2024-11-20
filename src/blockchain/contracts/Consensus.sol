// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract HybridConsensus {
    address public admin;
    uint public validatorCount;

    struct Validator {
        address validatorAddress;
        uint256 stake;
        uint256 reputation; // امتیاز اعتبار که براساس مدل هوش مصنوعی و dPoS بروز می‌شود
        bool isValidator;
        uint lastParticipationBlock; // آخرین بلاک که در آن شرکت داشته‌اند
    }

    struct Proposal {
        uint id;
        string description;
        uint voteCountYes;
        uint voteCountNo;
        mapping(address => bool) hasVoted;
    }

    mapping(address => Validator) public validators;
    mapping(address => address) public delegations; // نماینده‌ها
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

    constructor(address _daoAddress) {
        admin = _daoAddress;
    }

    // افزودن یک اعتبارسنج جدید با مدل PoA و مشارکت dPoS
    function addValidator(address validatorAddress, uint256 initialStake) external onlyAdmin {
        require(!validators[validatorAddress].isValidator, "Validator already exists");
        validators[validatorAddress] = Validator(validatorAddress, initialStake, 0, true, block.number);
        validatorList.push(validatorAddress);
        validatorCount++;
    }

    // حذف اعتبارسنج
    function removeValidator(address validatorAddress) external onlyAdmin {
        require(validators[validatorAddress].isValidator, "Validator not found");
        validators[validatorAddress].isValidator = false;
        validatorCount--;
    }

     // ایجاد پروپوزال جدید توسط مدیر
    function createProposal(string memory description) external onlyAdmin {
        proposalCount++;
        Proposal storage newProposal = proposals[proposalCount];
        newProposal.id = proposalCount;
        newProposal.description = description;
        newProposal.voteCountYes = 0;
        newProposal.voteCountNo = 0;
    }

    // تخصیص نماینده برای رأی‌دهی (dPoS)
    function delegateVote(address validatorAddress) external {
        require(validators[validatorAddress].isValidator, "Address is not a validator");
        delegations[msg.sender] = validatorAddress;
    }

    // رأی‌دهی توسط اعتبارسنج‌ها یا نمایندگان کاربران
    function voteProposal(uint proposalId, bool support) external {
        address voter = msg.sender;

        // بررسی اینکه آیا کاربر نماینده‌ای برای رأی دارد
        if (delegations[msg.sender] != address(0)) {
            voter = delegations[msg.sender];
        }

        require(validators[voter].isValidator, "Voter must be a validator or a delegate");
        
        Proposal storage proposal = proposals[proposalId];
        require(!proposal.hasVoted[voter], "Validator has already voted on this proposal");

        if (support) {
            proposal.voteCountYes++;
        } else {
            proposal.voteCountNo++;
        }

        // به‌روزرسانی امتیاز اعتبار و بلاک مشارکت
        validators[msg.sender].reputation += 1; // افزایش امتیاز اعتبار به ازای هر رأی
        validators[msg.sender].lastParticipationBlock = block.number;
        proposal.hasVoted[msg.sender] = true;
    }

    // تابع بررسی نتیجه رأی‌گیری
    function getProposalResult(uint proposalId) external view returns (string memory description, uint voteCountYes, uint voteCountNo) {
        Proposal storage proposal = proposals[proposalId];
        return (proposal.description, proposal.voteCountYes, proposal.voteCountNo);
    }

    // بررسی وضعیت اعتبارسنج بودن یک حساب
    function isValidator(address account) public view returns (bool) {
        return validators[account].isValidator;
    }

    // دریافت لیست اعتبارسنج‌ها
    function getValidators() public view returns (address[] memory) {
        return validatorList;
    }

    // پاداش‌دهی به اعتبارسنج‌ها براساس مشارکت
    function rewardValidators() external onlyAdmin {
        for (uint i = 0; i < validatorList.length; i++) {
            address validatorAddress = validatorList[i];
            Validator storage validator = validators[validatorAddress];
	    
	    // بررسی فعالیت اعتبارسنج‌ها و پاداش‌دهی به آن‌ها
            if (block.number - validator.lastParticipationBlock < 100) {// بررسی مشارکت در 100 بلاک اخیر
                validator.reputation += 10; // پاداش به اعتبارسنج‌های فعال
            } else {
                validator.reputation -= 1; // کاهش امتیاز اعتبار برای عدم فعالیت
            }
        }
    }
}