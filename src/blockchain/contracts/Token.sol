// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract Token is ERC20, Ownable {
    constructor(uint256 initialSupply) ERC20("Rayan Andish Token", "RATK") Ownable(msg.sender) {
        _mint(msg.sender, initialSupply); // تخصیص مقدار اولیه توکن به msg.sender
    }

    function mint(address to, uint256 amount) public onlyOwner {
        _mint(to, amount);
    }

    function burn(uint256 amount) public {
        _burn(msg.sender, amount);
    }
}
