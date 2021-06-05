import random

open_polls = []

class Poll:
    def __init__(self, creator, question):
        self.open_polls = open_polls.append(self)
        self.id = random.randint(1, 1000)
        self.creator = creator
        self.question = question
        self.votes_yes = 0
        self.votes_no = 0
        self.voters = {}

        print(f'Created Poll {self.id} by {creator}')
        print(f'Question: {question}')
        print(f'Open_Polls: {open_polls}')

    def vote(self, voter, decision):
        if voter not in self.voters:
            if decision == "yes":
                self.voters[voter] = 'yes'
                self.votes_yes = self.votes_yes + 1
            else:
                self.voters[voter] = 'no'
                self.votes_no = self.votes_no + 1
        else:
            if not self.voters[voter] == decision:
                if decision == "yes":
                    self.voters[voter] = 'yes'
                    self.votes_no = self.votes_no - 1
                    self.votes_yes = self.votes_yes + 1
                else:
                    self.voters[voter] = 'no'
                    self.votes_yes = self.votes_yes -1
                    self.votes_no = self.votes_no + 1
