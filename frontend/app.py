import logging

import streamlit as st
from meeting_agent.config import Settings
from meeting_agent.pipeline import ReviewError
from meeting_agent.schemas import DraftStatus, Priority, TicketDraft, TranscriptStatus
from meeting_agent.service import SetupError, build_app
from pydantic import ValidationError


logger = logging.getLogger(__name__)


@st.cache_resource
def load_app():
    return build_app(Settings())


def edited_ticket(draft, summary, description, assignee, due_date, priority) -> TicketDraft:
    return TicketDraft(
        summary=summary,
        description=description,
        source_quote=draft.ticket.source_quote,
        assignee=assignee,
        due_date=due_date,
        priority=priority,
        labels=draft.ticket.labels,
    )


def review_form(storage, pipeline, transcript, drafts) -> None:
    with st.form(f"review-{transcript.file_id}-{transcript.revision}"):
        answers = []
        for draft in drafts:
            ticket = draft.ticket
            key = f"draft-{draft.id}"
            st.subheader(ticket.summary)
            st.caption(f'Transcript quote: "{ticket.source_quote}"')
            decision = st.radio(
                "Decision",
                ["Approve", "Reject"],
                index=None,
                key=f"{key}-decision",
                horizontal=True,
            )
            summary = st.text_input("Summary", ticket.summary, key=f"{key}-summary")
            description = st.text_area("Description", ticket.description, key=f"{key}-description")
            owner, due, priority = st.columns(3)
            assignee = owner.text_input("Assignee", ticket.assignee or "", key=f"{key}-assignee")
            due_date = due.date_input("Due date", ticket.due_date, key=f"{key}-due")
            level = priority.selectbox(
                "Priority", list(Priority), list(Priority).index(ticket.priority), key=f"{key}-pri"
            )
            answers.append((draft, decision, summary, description, assignee, due_date, level))
            st.divider()
        submitted = st.form_submit_button("Save decisions and send approved items")

    if not submitted:
        return
    if any(decision is None for _, decision, *_ in answers):
        st.error("Choose Approve or Reject for every item. Nothing was sent.")
        return
    try:
        reviewed = [
            (draft, decision, edited_ticket(draft, *fields)) for draft, decision, *fields in answers
        ]
    except ValidationError as exc:
        st.error(f"Fix these fields first. Nothing was sent.\n\n{exc}")
        return
    for draft, decision, ticket in reviewed:
        status = DraftStatus.APPROVED if decision == "Approve" else DraftStatus.REJECTED
        storage.update_draft(draft.id, status, ticket)
    finish(pipeline, transcript)


def finish(pipeline, transcript) -> None:
    try:
        pipeline.finish_review(transcript.file_id, transcript.revision)
    except ReviewError as exc:
        st.error(str(exc))
    except Exception:
        # The details go to the server log, because they can include fragments of credentials.
        logger.exception("Sending failed for %s", transcript.name)
        st.error("Sending failed. You can retry without creating duplicates.")
    else:
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Meeting Agent Approvals")
    st.title("Meeting Agent Approvals")
    st.write("Nothing is sent to Jira, Slack or email until you approve it here.")
    try:
        storage, pipeline = load_app()
    except SetupError as exc:
        st.error(str(exc))
        return

    waiting = storage.list_transcripts(TranscriptStatus.AWAITING_APPROVAL)
    if not waiting:
        st.info("No transcripts are waiting for review.")
    for transcript in waiting:
        st.header(transcript.name)
        drafts = storage.list_drafts(DraftStatus.PENDING, transcript.file_id, transcript.revision)
        if drafts:
            review_form(storage, pipeline, transcript, drafts)
        elif st.button("Retry sending", key=f"retry-{transcript.file_id}-{transcript.revision}"):
            finish(pipeline, transcript)


main()
