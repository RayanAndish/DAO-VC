// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Consensus {
    address public admin;
    mapping(address => bool) public validators;
    address[] public validatorList;

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can add validators");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function addValidator(address validator) external onlyAdmin {
        require(!validators[validator], "Validator already added");
        validators[validator] = true;
        validatorList.push(validator);
    }

    function removeValidator(address validator) external onlyAdmin {
        require(validators[validator], "Validator not found");
        validators[validator] = false;
    }

    function isValidator(address account) public view returns (bool) {
        return validators[account];
    }

    function getValidators() public view returns (address[] memory) {
        return validatorList;
    }
}
