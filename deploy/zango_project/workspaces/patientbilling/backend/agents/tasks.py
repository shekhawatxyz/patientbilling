from zango.ai import get_agent


def run_claim_validator(claim_id):
    agent = get_agent("claim-validator")
    agent.run(variables={"claim_id": str(claim_id)})


def run_denial_analyzer(claim_id):
    agent = get_agent("denial-analyzer")
    agent.run(variables={"claim_id": str(claim_id)})


def run_appeal_drafter(claim_id):
    agent = get_agent("appeal-drafter")
    agent.run(variables={"claim_id": str(claim_id)})
