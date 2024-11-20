const Web3 = require('web3');
const contract = require('@truffle/contract');
const TokenArtifact = require('./build/contracts/Token.json');

const deployContract = async () => {
    const web3 = new Web3('http://172.16.22.120:8545');
    const accounts = await web3.eth.getAccounts();
    const Token = contract(TokenArtifact);
    Token.setProvider(web3.currentProvider);
    const instance = await Token.new(1000000, { from: accounts[0] });
    console.log("Token deployed at:", instance.address);
};

deployContract();
