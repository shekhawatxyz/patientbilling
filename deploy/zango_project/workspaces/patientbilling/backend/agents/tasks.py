from zango.ai import get_agent

from .tools import _current_claim_id


def run_claim_validator(claim_id):
    token = _current_claim_id.set(str(claim_id))
    try:
        agent = get_agent("claim-validator")
        agent.run(variables={"claim_id": str(claim_id)}, triggered_by="task")
    finally:
        _current_claim_id.reset(token)


def run_denial_analyzer(claim_id):
    token = _current_claim_id.set(str(claim_id))
    try:
        agent = get_agent("denial-analyzer")
        agent.run(variables={"claim_id": str(claim_id)}, triggered_by="task")
    finally:
        _current_claim_id.reset(token)
    run_appeal_drafter(claim_id)


def run_appeal_drafter(claim_id):
    token = _current_claim_id.set(str(claim_id))
    try:
        agent = get_agent("appeal-drafter")
        agent.run(variables={"claim_id": str(claim_id)}, triggered_by="task")
    finally:
        _current_claim_id.reset(token)
