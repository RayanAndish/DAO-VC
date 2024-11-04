// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Consensus {
    address public admin;
    mapping(address => bool) public validators;

    constructor() {
        admin = msg.sender;
    }

    function addValidator(address validator) external {
        require(msg.sender == admin, "Only admin can add validators");
        validators[validator] = true;
    }

    function isValidator(address account) public view returns (bool) {
        return validators[account];
    }
}
