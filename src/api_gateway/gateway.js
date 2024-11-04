const express = require('express');
const Web3 = require('web3');
const VotingArtifact = require('./contracts/Voting.json');
const app = express();

app.use(express.json());

const web3 = new Web3('http://172.16.22.120:8545');
const Voting = new web3.eth.Contract(VotingArtifact.abi, 'contract_address_here');

app.post('/createProposal', async (req, res) => {
    const { description } = req.body;
    const accounts = await web3.eth.getAccounts();
    await Voting.methods.createProposal(description).send({ from: accounts[0] });
    res.send({ status: 'Proposal created' });
});

app.post('/vote', async (req, res) => {
    const { proposalId } = req.body;
    const accounts = await web3.eth.getAccounts();
    await Voting.methods.vote(proposalId).send({ from: accounts[0] });
    res.send({ status: 'Voted' });
});

app.listen(8080, () => console.log('API Gateway running on port 8080'));
