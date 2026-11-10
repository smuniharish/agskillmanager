"""A local review console with a stable async lifecycle across UI reruns."""

from __future__ import annotations

import os

import streamlit as st
from _dashboard import Dashboard

from skill_manager import (
    Skill,
    SkillLifecycleState,
    SkillManagerError,
    SkillMetadata,
)

st.set_page_config(page_title="Skill Manager", layout="wide")
st.title("Skill Manager lifecycle console")
st.caption("Local demonstration. Enforce authentication and durable review storage in production.")
if message := st.session_state.pop("notice", None):
    st.success(message)


def notify(message: str) -> None:
    st.session_state["notice"] = message
    st.rerun()


@st.cache_resource
def dashboard(root: str) -> Dashboard:
    return Dashboard(root)


service = dashboard(os.getenv("SKILL_MANAGER_UI_SKILLS_DIR", "skills/streamlit"))
st.session_state["dashboard"] = service
catalog_tab, create_tab, review_tab = st.tabs(["Catalog", "Create or generate", "Review"])

try:
    with create_tab:
        with st.form("create"):
            name = st.text_input("Name", value="summarize-ticket", key="register-name")
            description = st.text_input("Description", value="Summarize a support ticket.")
            instructions = st.text_area(
                "Instructions", value="Use only supplied facts.\nRemove personal data."
            )
            submitted = st.form_submit_button("Register human Skill")
        if submitted:
            service.register(
                Skill(
                    metadata=SkillMetadata(name=name, version="1.0.0", description=description),
                    instructions=tuple(line for line in instructions.splitlines() if line.strip()),
                )
            )
            notify("Human Skill registered.")
        prompt = st.text_area("Generation task", value="Create safe support-ticket instructions.")
        model = st.checkbox("Use a live model (requires environment credentials)")
        if st.button("Generate pending candidate"):
            if model and not (os.getenv("EXPLABS_API_KEY") or os.getenv("OPENAI_API_KEY")):
                raise ValueError("Set EXPLABS_API_KEY or OPENAI_API_KEY first.")
            service.generate(prompt, model=model)
            notify("Candidate queued for review.")

    skills = service.skills()
    with review_tab:
        pending = [
            skill
            for skill in skills
            if skill.lifecycle.state is SkillLifecycleState.PENDING_APPROVAL
        ]
        selected = st.selectbox(
            "Pending candidate",
            pending,
            format_func=lambda skill: (
                f"{skill.metadata.name} / revision {skill.revision} / {skill.skill_id}"
            ),
        )
        reviewer = st.text_input("Reviewer", value="local-reviewer")
        feedback = st.text_area("Review feedback", value="Add explicit privacy checks.")
        if selected is not None:
            st.json(selected.model_dump(mode="json"))
            if st.button("Approve"):
                service.approve(selected.skill_id, reviewer)
                notify("Candidate approved.")
            if st.button("Reject"):
                service.reject(selected.skill_id, reviewer, feedback)
                notify("Rejection retained for audit.")
        rejected = [
            skill
            for skill in service.skills()
            if skill.lifecycle.state is SkillLifecycleState.REJECTED
        ]
        parent = st.selectbox(
            "Rejected parent",
            rejected,
            format_func=lambda skill: f"{skill.metadata.name} / revision {skill.revision}",
        )
        if parent is not None and st.button("Regenerate from feedback"):
            if model and not (os.getenv("EXPLABS_API_KEY") or os.getenv("OPENAI_API_KEY")):
                raise ValueError("Set EXPLABS_API_KEY or OPENAI_API_KEY first.")
            service.generate(prompt, model=model, parent=parent.skill_id)
            notify("Revised candidate queued for review.")

    with catalog_tab:
        current = service.skills()
        st.metric("Registered revisions", len(current))
        st.metric(
            "Pending review",
            sum(s.lifecycle.state is SkillLifecycleState.PENDING_APPROVAL for s in current),
        )
        st.json([skill.model_dump(mode="json") for skill in current])
        if service.manager.source_errors:
            st.error(str(dict(service.manager.source_errors)))
        if service.manager.observability_errors:
            st.error("Observability failed; inspect application logs.")
except (SkillManagerError, ValueError, RuntimeError) as error:
    st.error(str(error))
