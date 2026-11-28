"""The planner proposes data; this contract decides what the engine can accept."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=64_000)


class ExactEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=240)
    old: str = Field(min_length=1, max_length=64_000)
    new: str = Field(max_length=64_000)


class ProposalMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rationale: str = Field(min_length=10, max_length=8000)
    plan: list[str] = Field(min_length=1, max_length=8)


class ProductionProposal(ProposalMetadata):
    edits: list[Edit] = Field(min_length=1, max_length=5)


class RepairProposal(ProductionProposal):
    regression: str = Field(min_length=1, max_length=64_000)


class ExactProductionProposal(ProposalMetadata):
    edits: list[ExactEdit] = Field(min_length=1, max_length=5)


class ExactRepairProposal(ExactProductionProposal):
    regression: str = Field(min_length=1, max_length=64_000)


class EditMatchError(ValueError):
    """An exact edit cannot be materialized against the reviewed source."""


def parse_proposal(value: object, *, supplied_regression: str | None = None) -> dict:
    try:
        if supplied_regression is not None:
            production = ProductionProposal.model_validate(value)
            value = {**production.model_dump(), "regression": supplied_regression}
        proposal = RepairProposal.model_validate(value)
        if any(not step.strip() or len(step) > 1000 for step in proposal.plan):
            raise ValueError("Plan steps must be nonempty and bounded")
        return proposal.model_dump()
    except ValidationError:
        # Pydantic error strings include input values; never persist private source in errors.
        raise ValueError("Repair proposal violates the required schema or size limits") from None


def parse_exact_proposal(value: object, reviewed_files: dict[str, str], *, supplied_regression: str | None) -> dict:
    proposal_type = ExactRepairProposal if supplied_regression is None else ExactProductionProposal
    try:
        proposal = proposal_type.model_validate(value)
    except ValidationError:
        raise ValueError("Repair proposal violates the required schema or size limits") from None

    edits = []
    for edit in proposal.edits:
        if edit.path not in reviewed_files:
            raise EditMatchError("Proposed edit does not target a reviewed file")
        source = reviewed_files[edit.path]
        start = source.find(edit.old)
        if start == -1 or source.find(edit.old, start + 1) != -1:
            raise EditMatchError("Proposed edit must match exactly one location in the reviewed file")
        edits.append(dict(path=edit.path, content=source[:start] + edit.new + source[start + len(edit.old):]))
    return parse_proposal({**proposal.model_dump(), "edits": edits}, supplied_regression=supplied_regression)


def output_schema(*, production_only: bool = False, exact_edits: bool = False) -> dict:
    """Use the strict structural subset; enforce all size constraints again locally."""
    proposal = ProductionProposal if production_only else RepairProposal
    if exact_edits:
        proposal = ExactProductionProposal if production_only else ExactRepairProposal
    schema = proposal.model_json_schema()

    def structural(node: object) -> None:
        if isinstance(node, dict):
            for key in ("minLength", "maxLength", "minItems", "maxItems"):
                node.pop(key, None)
            for value in node.values():
                structural(value)
        elif isinstance(node, list):
            for value in node:
                structural(value)

    structural(schema)
    return schema
