// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

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
    mapping(uint => mapping(uint => uint)) public voteOptions; // گزینه‌های مختلف برای هر پروپوزال

    uint256 public votingFeeRate;
    address public feeCollector;

    event ProposalCreated(uint indexed proposalId, string description, uint256 startTime, uint256 endTime);
    event Voted(uint indexed proposalId, address voter, uint option);

    modifier onlyWithinTime(uint proposalId) {
        require(block.timestamp >= proposals[proposalId].startTime, "Voting has not started");
        require(block.timestamp <= proposals[proposalId].endTime, "Voting period has ended");
        _;
    }

    constructor(uint256 _votingFeeRate, address _feeCollector, address initialOwner) Ownable(initialOwner) {
        votingFeeRate = _votingFeeRate;
        feeCollector = _feeCollector;
    }

    // تنظیم آدرس دریافت‌کننده کارمزد توسط مالک
    function setFeeCollector(address _feeCollector) external onlyOwner {
        feeCollector = _feeCollector;
    }

    // تابع برای ایجاد پروپوزال جدید با زمان‌بندی و گزینه‌های مختلف
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
        newProposal.voteCounts = new uint[](options.length); // تعداد رأی‌های هر گزینه
        newProposal.finalized = false;

        emit ProposalCreated(proposalCount, description, startTime, endTime);
    }

    // رأی‌گیری برای یک پروپوزال با پرداخت کارمزد و انتخاب گزینه
    function vote(uint proposalId, uint option) external payable onlyWithinTime(proposalId) {
        Proposal storage proposal = proposals[proposalId];
        require(!hasVoted[msg.sender][proposalId], "You have already voted on this proposal");
        require(option < proposal.voteCounts.length, "Invalid voting option");

        require(msg.value >= votingFeeRate, "Insufficient voting fee");
        payable(feeCollector).transfer(msg.value); // انتقال کارمزد رأی به آدرس مشخص‌شده

        hasVoted[msg.sender][proposalId] = true;
        proposal.voteCounts[option]++;

        emit Voted(proposalId, msg.sender, option);
    }

    // مشاهده نتیجه پروپوزال و تعداد آرای هر گزینه
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

    // مشاهده وضعیت پروپوزال برای اطلاع از پایان یا ادامه‌ی رأی‌گیری
    function isVotingActive(uint proposalId) public view returns (bool) {
        Proposal storage proposal = proposals[proposalId];
        return block.timestamp >= proposal.startTime && block.timestamp <= proposal.endTime;
    }
}