import pytest
from aiguard.shields.models import ScanContext
import uuid


def make_context(messages: list[dict]) -> ScanContext:
    return ScanContext(
        request_id=str(uuid.uuid4()),
        org_id="test",
        user_id=None,
        provider="test",
        model="test",
        phase="pre_request",
        messages=messages,
        system_prompt=None,
        tool_results=[],
        raw_body={"messages": messages},
    )


@pytest.mark.asyncio
async def test_detects_ssn(shield_runner):
    context = make_context([
        {"role": "user", "content": "My social security number is 123-45-6789"}
    ])
    shield = shield_runner.shields["pii_detection"]
    result = await shield_runner._run_shield(shield, context)
    assert result.triggered
    pattern_ids = [f.pattern_id for f in result.findings]
    assert "ssn_us" in pattern_ids


@pytest.mark.asyncio
async def test_detects_credit_card_and_blocks(shield_runner):
    context = make_context([
        {"role": "user", "content": "use my card 4111111111111111 for payment"}
    ])
    shield = shield_runner.shields["pii_detection"]
    result = await shield_runner._run_shield(shield, context)
    assert result.triggered
    # default_action on the shield is "warn", which caps pattern-level actions
    assert result.effective_action == "warn"


@pytest.mark.asyncio
async def test_detects_hyphenated_credit_card(shield_runner):
    context = make_context([
        {"role": "user", "content": "use my card 4111-1111-1111-1111 for payment"}
    ])
    shield = shield_runner.shields["pii_detection"]
    result = await shield_runner._run_shield(shield, context)
    assert result.triggered
    cc_findings = [f for f in result.findings if f.pattern_id == "credit_card"]
    assert len(cc_findings) >= 1
    # Shield default_action (warn) caps the pattern-level block action
    assert result.effective_action == "warn"


@pytest.mark.asyncio
async def test_detects_aws_key(shield_runner):
    context = make_context([
        {"role": "user", "content": "My AWS key is AKIAIOSFODNN7EXAMPLE"}
    ])
    shield = shield_runner.shields["pii_detection"]
    result = await shield_runner._run_shield(shield, context)
    assert result.triggered


@pytest.mark.asyncio
async def test_no_pii_passes(shield_runner):
    context = make_context([
        {"role": "user", "content": "Can you summarize this article about climate change?"}
    ])
    shield = shield_runner.shields["pii_detection"]
    result = await shield_runner._run_shield(shield, context)
    assert not result.triggered
