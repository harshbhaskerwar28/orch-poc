import streamlit as st
import requests
import json
import uuid
from typing import List

# Page config
st.set_page_config(
    page_title="Doctor Recommendation - Deployed Tester",
    page_icon="🏥",
    layout="wide",
)

# Deployed API endpoint (full path)
DEPLOYED_ORCH_URL = "https://dev-api-gateway.aesthatiq.com/mcp-orch-service/orch"


def make_api_request(payload: dict) -> dict:
    """POST to deployed orch endpoint and return dict with success/data or error."""
    try:
        resp = requests.post(DEPLOYED_ORCH_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def regenerate_ids_each_run():
    """Always regenerate session_id and user_id on every rerun."""
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.user_id = f"user_{str(uuid.uuid4())[:8]}"


def render_json_response_block(response_payload):
    """Render a rich view for dict/JSON string; fallback to plain text for others."""
    # Normalize to dict if possible
    parsed = None
    if isinstance(response_payload, dict):
        parsed = response_payload
    elif isinstance(response_payload, str):
        try:
            parsed = json.loads(response_payload)
        except (json.JSONDecodeError, TypeError):
            parsed = None

    if isinstance(parsed, dict):
        # Primary answer
        if parsed.get("answer"):
            st.markdown(parsed["answer"])

        # Booking context
        if parsed.get("booking_context"):
            with st.expander("Booking Details"):
                ctx = parsed["booking_context"]
                st.markdown(f"**Service:** {ctx.get('service', 'N/A')}")
                st.markdown(f"**Doctor:** {ctx.get('doctor', 'N/A')}")
                st.markdown(f"**Date:** {ctx.get('date', 'N/A')}")
                st.markdown(f"**Time:** {ctx.get('time', 'N/A')}")

        # Information gathered
        if parsed.get("information_gathered"):
            st.markdown("#### Information Gathered")
            for i, info in enumerate(parsed["information_gathered"], 1):
                st.markdown(f"{i}. {info}")

        # Assessment progress
        if "assessment_progress" in parsed:
            if parsed["assessment_progress"] == "complete":
                st.success("Assessment Complete")
            else:
                st.info(f"Assessment Progress: {parsed['assessment_progress']}")

        # Recommendations
        if parsed.get("recommendations"):
            st.markdown("#### Recommendations")
            for i, rec in enumerate(parsed["recommendations"], 1):
                st.markdown(f"{i}. {rec}")

        # Next steps
        if parsed.get("next_steps"):
            st.markdown("#### Next Steps")
            for i, step in enumerate(parsed["next_steps"], 1):
                st.markdown(f"{i}. {step}")

        # Sources
        if parsed.get("sources"):
            with st.expander("Sources"):
                for source in parsed["sources"]:
                    st.markdown(f"- {source}")
        return

    # Fallback: show as plain text
    st.markdown(response_payload if isinstance(response_payload, str) else str(response_payload))


def render_mcq_if_present(raw_content: str, key_prefix: str, slot_id: str | None):
    """Render MCQ inputs if payload indicates an MCQ; return True if MCQ handled (blocks free input)."""
    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return False

    if not isinstance(parsed, dict):
        return False

    if parsed.get("question_type") != "mcq":
        return False

    mcq_question = parsed.get("mcq_question") or "Please select an option:"
    options: List[str] = parsed.get("mcq_options") or []
    if not options:
        return False

    st.markdown(f"#### {mcq_question}")
    selected = st.radio("Choose answer:", options, key=f"{key_prefix}_mcq_radio", index=None)

    submitted = st.button("Submit Answer", key=f"{key_prefix}_mcq_submit")
    if submitted:
        if not selected:
            st.warning("Please select an option before submitting.")
        else:
            user_response = f"Selected: {selected}"
            payload = {
                "session_id": st.session_state.session_id,
                "user_id": st.session_state.user_id,
                "input": user_response,
            }
            if slot_id:
                payload["slot_id"] = slot_id

            with st.spinner("Processing your answer..."):
                result = make_api_request(payload)

            if result["success"]:
                data = result["data"]
                if "answer" in data:
                    response_text = json.dumps({
                        "answer": data.get("answer"),
                        "question_type": data.get("question_type", "text"),
                        "mcq_options": data.get("mcq_options", []),
                        "mcq_question": data.get("mcq_question", ""),
                        "booking_context": data.get("booking_context", {}),
                        "status": data.get("status", "progress"),
                    })
                else:
                    response_text = data.get("response", "No response received")

                render_json_response_block(response_text)
                # If the new response is again MCQ, keep flow; caller will call this again on rerun
                st.rerun()
            else:
                st.error(result.get("error", "Unknown error"))

    return True


def ask_mode():
    st.subheader("Ask")

    if "ask_history" not in st.session_state:
        st.session_state.ask_history = []

    for idx, msg in enumerate(st.session_state.ask_history):
        with st.chat_message(msg["role"]):
            render_json_response_block(msg["content"]) if msg["role"] == "assistant" else st.markdown(msg["content"]) 

    prompt = st.chat_input("Ask about healthcare services...")
    if prompt:
        st.session_state.ask_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        payload = {
            "session_id": st.session_state.session_id,
            "user_id": st.session_state.user_id,
            "input": prompt,
        }
        with st.spinner("Processing..."):
            result = make_api_request(payload)

        if result["success"]:
            data = result["data"]
            if "answer" in data:
                response_text = json.dumps({
                    "answer": data.get("answer"),
                    "question_type": data.get("question_type", "text"),
                    "mcq_options": data.get("mcq_options", []),
                    "mcq_question": data.get("mcq_question", ""),
                    "booking_context": data.get("booking_context", {}),
                    "status": data.get("status", "progress"),
                })
            else:
                response_text = data.get("response", "No response received")

            st.session_state.ask_history.append({"role": "assistant", "content": response_text})

            with st.chat_message("assistant"):
                # If MCQ, render picker and handle
                if not render_mcq_if_present(response_text, key_prefix=f"ask_{len(st.session_state.ask_history)}", slot_id=None):
                    render_json_response_block(response_text)
        else:
            err = result["error"]
            st.session_state.ask_history.append({"role": "assistant", "content": f"Error: {err}"})
            with st.chat_message("assistant"):
                st.error(err)


def booking_chat_mode():
    st.subheader("Booking Chat")

    if "booking_history" not in st.session_state:
        st.session_state.booking_history = []

    col1, col2 = st.columns([3, 1])
    with col1:
        slot_id = st.text_input("Slot ID", placeholder="e.g., slot_123", key="slot_id_input_dep")
    with col2:
        if st.button("Set Slot ID") and slot_id:
            st.session_state.current_slot_id = slot_id
            st.rerun()

    if "current_slot_id" in st.session_state and st.session_state.current_slot_id:
        st.info(f"Current Slot ID: {st.session_state.current_slot_id}")

        # Auto-fetch booking details/message if empty history (no chat input, agent triggers first)
        if not st.session_state.booking_history:
            payload = {
                "session_id": st.session_state.session_id,
                "user_id": st.session_state.user_id,
                "slot_id": st.session_state.current_slot_id
                # no 'input' key at all
            }
            with st.spinner("Fetching booking details..."):
                result = make_api_request(payload)
            if result["success"]:
                data = result["data"]
                if "answer" in data:
                    response_text = json.dumps({
                        "answer": data.get("answer"),
                        "question_type": data.get("question_type", "text"),
                        "mcq_options": data.get("mcq_options", []),
                        "mcq_question": data.get("mcq_question", ""),
                        "booking_context": data.get("booking_context", {}),
                        "status": data.get("status", "progress"),
                    })
                else:
                    response_text = data.get("response", "No response received")
                st.session_state.booking_history.append({"role": "assistant", "content": response_text})
                st.rerun()
            else:
                st.error(result.get("error", "Unknown error"))

        # Render history
        for idx, msg in enumerate(st.session_state.booking_history):
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    # Try MCQ render; if not MCQ, show rich JSON
                    if not render_mcq_if_present(msg["content"], key_prefix=f"book_hist_{idx}", slot_id=st.session_state.current_slot_id):
                        render_json_response_block(msg["content"])
                else:
                    st.markdown(msg["content"])

        # If last assistant message is MCQ, free input is blocked by the MCQ submit flow
        # Otherwise, show chat input
        show_free_input = True
        if st.session_state.booking_history:
            try:
                last = st.session_state.booking_history[-1]
                parsed = json.loads(last["content"]) if last["role"] == "assistant" else None
                if isinstance(parsed, dict) and parsed.get("question_type") == "mcq":
                    show_free_input = False
            except Exception:
                pass

        if show_free_input:
            prompt = st.chat_input("Ask questions about this booking...")
            if prompt:
                st.session_state.booking_history.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                payload = {
                    "session_id": st.session_state.session_id,
                    "user_id": st.session_state.user_id,
                    "input": prompt,
                    "slot_id": st.session_state.current_slot_id,
                }
                with st.spinner("Processing..."):
                    result = make_api_request(payload)

                if result["success"]:
                    data = result["data"]
                    if "answer" in data:
                        response_text = json.dumps({
                            "answer": data.get("answer"),
                            "question_type": data.get("question_type", "text"),
                            "mcq_options": data.get("mcq_options", []),
                            "mcq_question": data.get("mcq_question", ""),
                            "booking_context": data.get("booking_context", {}),
                            "status": data.get("status", "progress"),
                        })
                    else:
                        response_text = data.get("response", "No response received")
                    st.session_state.booking_history.append({"role": "assistant", "content": response_text})
                    with st.chat_message("assistant"):
                        if not render_mcq_if_present(response_text, key_prefix=f"book_{len(st.session_state.booking_history)}", slot_id=st.session_state.current_slot_id):
                            render_json_response_block(response_text)
                else:
                    err = result["error"]
                    st.session_state.booking_history.append({"role": "assistant", "content": f"Error: {err}"})
                    with st.chat_message("assistant"):
                        st.error(err)
    else:
        st.info("Enter a Slot ID and click Set Slot ID to start.")


def upload_urls_mode():
    st.subheader("Upload (URLs)")
    st.markdown("Paste one or more file URLs (PDF/JPG/PNG), separated by new lines.")

    default_text = ""
    urls_text = st.text_area("File URLs", value=default_text, height=150, placeholder="https://example.com/file1.pdf\nhttps://example.com/xray1.png")
    process = st.button("Process URLs", type="primary")

    if process:
        file_urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        if not file_urls:
            st.warning("Please provide at least one URL.")
            return

        payload = {
            "session_id": st.session_state.session_id,
            "user_id": st.session_state.user_id,
            "file_urls": file_urls,
        }
        with st.spinner("Processing files..."):
            result = make_api_request(payload)

        if result["success"]:
            data = result["data"]
            st.success("Files processed successfully!")
            response_text = data.get("response", "{}")
            try:
                parsed = json.loads(response_text)
                if isinstance(parsed, dict) and parsed.get("processed_files"):
                    st.markdown("### File Processing Results")
                    processed_files = parsed["processed_files"]
                    total_processed = parsed.get("total_processed", len(processed_files))
                    total_successful = parsed.get("total_successful", sum(1 for f in processed_files if f.get("success")))

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Total Files", total_processed)
                    with c2:
                        st.metric("Successfully Processed", total_successful)
                    with c3:
                        rate = (total_successful / total_processed * 100) if total_processed else 0
                        st.metric("Success Rate", f"{rate:.1f}%")

                    st.markdown("---")
                    for i, info in enumerate(processed_files, 1):
                        st.markdown(f"### File {i}: {info.get('file_url', 'Unknown').split('/')[-1]}")
                        if info.get("success"):
                            st.success("Successfully Processed")
                        else:
                            st.error("Processing Failed")

                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**File Type:** {info.get('file_type', 'Unknown').upper()}")
                            st.markdown(f"**Healthcare Related:** {'Yes' if info.get('is_healthcare_related', False) else 'No'}")
                        with col2:
                            st.markdown(f"**File URL:** `{info.get('file_url', 'N/A')}`")

                        if info.get("summary"):
                            st.markdown("#### Summary")
                            st.markdown(info["summary"])
                        if info.get("description"):
                            st.markdown("#### Description")
                            st.markdown(info["description"])
                        if info.get("error"):
                            st.markdown("#### Error")
                            st.error(info["error"])

                        if i < len(processed_files):
                            st.markdown("---")
                else:
                    st.markdown("### Processing Result")
                    st.text_area("Result", response_text, height=200, disabled=True, label_visibility="collapsed")
            except (json.JSONDecodeError, TypeError):
                st.markdown("### Processing Result")
                st.text_area("Result", response_text, height=200, disabled=True, label_visibility="collapsed")

            if data.get("booking_summary"):
                st.markdown("### Booking Summary")
                st.json(data["booking_summary"])
        else:
            st.error(f"File processing failed: {result['error']}")


def main():
    # Regenerate IDs on every reload
    regenerate_ids_each_run()

    st.title("🏥 Doctor Recommendation System (Deployed)")
    st.markdown("---")

    # On-page mode buttons (Ask, Booking Chat, Upload)
    if "dep_selected_mode" not in st.session_state:
        st.session_state.dep_selected_mode = "Ask"

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💬 Ask", use_container_width=True):
            st.session_state.dep_selected_mode = "Ask"
    with b2:
        if st.button("📅 Booking Chat", use_container_width=True):
            st.session_state.dep_selected_mode = "Booking Chat"
    with b3:
        if st.button("📤 Upload (URLs)", use_container_width=True):
            st.session_state.dep_selected_mode = "Upload"

    # IDs panel
    st.caption(f"Session ID: {st.session_state.session_id}")
    st.caption(f"User ID: {st.session_state.user_id}")

    st.markdown("---")

    if st.session_state.dep_selected_mode == "Ask":
        ask_mode()
    elif st.session_state.dep_selected_mode == "Booking Chat":
        booking_chat_mode()
    elif st.session_state.dep_selected_mode == "Upload":
        upload_urls_mode()


if __name__ == "__main__":
    main()


