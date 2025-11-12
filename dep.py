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
        resp = requests.post(DEPLOYED_ORCH_URL, json=payload, timeout=240)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}


def ensure_ids_once():
    """Initialize session_id and user_id only if not already set."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"user_{str(uuid.uuid4())[:8]}"

def reset_session_ids_and_state():
    """Regenerate IDs on demand and clear chat contexts, then rerun."""
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.user_id = f"user_{str(uuid.uuid4())[:8]}"
    # Clear histories/contexts to avoid mixing sessions
    for key in [
        "ask_history",
        "booking_history",
        "post_history",
        "post_ctx",
        "current_slot_id",
        "slot_id_input_dep",
        "post_slot_id",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def _normalize_nested_json(payload):
    """Best-effort to unwrap double-encoded API payloads (response/answer as JSON strings)."""
    current = payload
    # Attempt up to 3 unwrapping passes
    for _ in range(3):
        # String → try JSON
        if isinstance(current, str):
            try:
                maybe = json.loads(current)
                current = maybe
            except (json.JSONDecodeError, TypeError):
                break
        # Dict with inner JSON strings
        if isinstance(current, dict):
            # Prefer inner 'response' if it's a JSON string
            inner = current.get("response")
            if isinstance(inner, str):
                try:
                    current = json.loads(inner)
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            # Or inner 'answer' if it's a JSON string containing the full object
            inner_ans = current.get("answer")
            if isinstance(inner_ans, str) and inner_ans.strip().startswith("{"):
                try:
                    current = json.loads(inner_ans)
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
        break
    return current


def _prepare_response_content(data):
    """Normalize API responses into a JSON string with expected keys."""
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return json.dumps(data)

    payload = {}

    def _add(key, alias=None):
        value = data.get(key)
        if value in (None, "", [], {}):
            if alias:
                value = data.get(alias)
        if value not in (None, "", [], {}):
            payload[key] = value

    for item in [
        "answer",
        "question_type",
        "mcq_question",
        "mcq_options",
        "booking_context",
        "assessment_progress",
        "recommendations",
        "next_steps",
        "sources",
        "success",
        "treatment_plan",
        "additional_recommendations",
        "warnings",
        "products",
        "lab_tests",
        "chat_summary",
    ]:
        if isinstance(data.get(item), (dict, list)) and not data.get(item):
            continue
        _add(item)

    # Backwards compatibility for legacy keys
    _add("status")
    _add("response")

    if not payload and "response" in data:
        inner = data["response"]
        if isinstance(inner, (dict, list)):
            return _prepare_response_content(inner)
        if inner not in (None, ""):
            payload["response"] = inner

    if not payload and "answer" in data:
        payload["answer"] = data["answer"]

    if not payload:
        return json.dumps(data)

    return json.dumps(payload)


def render_json_response_block(response_payload):
    """Render a rich view for dict/JSON string; fallback to plain text for others."""
    parsed = _normalize_nested_json(response_payload)
    
    if isinstance(parsed, dict):
        # Show main answer text
        if parsed.get("answer"):
            st.markdown(parsed["answer"])
        elif parsed.get("response"):
            resp_val = parsed["response"]
            if isinstance(resp_val, str):
                st.markdown(resp_val)
            else:
                st.json(resp_val)

        # Display recommendations, next steps, chat summary
        if isinstance(parsed.get("recommendations"), list) and parsed["recommendations"]:
            st.markdown("#### Recommendations")
            for rec in parsed["recommendations"]:
                st.markdown(f"- {rec}")

        if isinstance(parsed.get("next_steps"), list) and parsed["next_steps"]:
            st.markdown("#### Next Steps")
            for step in parsed["next_steps"]:
                st.markdown(f"- {step}")

        if isinstance(parsed.get("additional_recommendations"), list) and parsed["additional_recommendations"]:
            st.markdown("#### Additional Recommendations")
            for item in parsed["additional_recommendations"]:
                st.markdown(f"- {item}")

        if isinstance(parsed.get("warnings"), list) and parsed["warnings"]:
            st.markdown("#### Warnings")
            for warn in parsed["warnings"]:
                st.markdown(f"- {warn}")

        summary_content = (
            parsed.get("assessment_summary")
            or parsed.get("booking_summary")
            or parsed.get("summary")
        )
        if summary_content:
            st.markdown("#### Summary")
            if isinstance(summary_content, list):
                for item in summary_content:
                    st.markdown(f"- {item}")
            else:
                st.markdown(summary_content)

        if parsed.get("chat_summary"):
            st.markdown("#### Chat Summary")
            st.markdown(parsed["chat_summary"])

        # Minimal booking context card if present
        ctx = parsed.get("booking_context")
        if isinstance(ctx, dict) and any(ctx.get(k) for k in ("service", "doctor", "date", "time")):
            with st.container(border=True):
                st.markdown("**Booking Details**")
                cols = st.columns(2)
                with cols[0]:
                    st.caption(f"Service: {ctx.get('service', 'N/A')}")
                    st.caption(f"Doctor: {ctx.get('doctor', 'N/A')}")
                with cols[1]:
                    st.caption(f"Date: {ctx.get('date', 'N/A')}")
                    st.caption(f"Time: {ctx.get('time', 'N/A')}")

        # Assessment progress
        progress = parsed.get("assessment_progress") or parsed.get("status")
        if isinstance(progress, str):
            st.caption(f"Assessment progress: {progress}")

        if isinstance(parsed.get("sources"), list) and parsed["sources"]:
            st.caption(f"Sources: {', '.join(str(src) for src in parsed['sources'])}")

        if parsed.get("success") is not None:
            st.caption(f"Success: {parsed['success']}")

        # Render products if present
        if isinstance(parsed.get("products"), list) and parsed.get("products"):
            st.markdown("---")
            with st.expander("Products", expanded=True):
                for product in parsed.get("products", []):
                    st.markdown(f"- {product}")

        # Render lab tests if present
        if isinstance(parsed.get("lab_tests"), list) and parsed.get("lab_tests"):
            st.markdown("---")
            with st.expander("Lab Tests", expanded=True):
                for test in parsed.get("lab_tests", []):
                    st.markdown(f"- {test}")

        return

    # Fallback: show as plain text
    st.markdown(response_payload if isinstance(response_payload, str) else str(response_payload))


def render_mcq_if_present(raw_content: str, key_prefix: str, slot_id: str | None):
    """Render MCQ inputs if payload indicates an MCQ; return True if MCQ handled (blocks free input)."""
    parsed = _normalize_nested_json(raw_content)
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
            user_response = selected
            with st.chat_message("user"):
                st.markdown(selected)
            user_msg = {"role": "user", "content": selected}
            if slot_id and st.session_state.get("booking_history") is not None:
                st.session_state.booking_history.append(user_msg)
            elif st.session_state.get("post_ctx") is not None and st.session_state.get("post_history") is not None:
                st.session_state.post_history.append(user_msg)
            elif st.session_state.get("ask_history") is not None:
                st.session_state.ask_history.append(user_msg)
            payload = {
                "session_id": st.session_state.session_id,
                "user_id": st.session_state.user_id,
                "input": user_response,
            }
            payload["mcq_selected_option"] = selected
            try:
                payload["mcq_selected_index"] = options.index(selected)
            except ValueError:
                pass
            payload["mcq_question"] = mcq_question
            if slot_id:
                payload["slot_id"] = slot_id

            with st.spinner("Processing your answer..."):
                result = make_api_request(payload)

            if result["success"]:
                response_text = _prepare_response_content(result.get("data", {}))

                # Append to the appropriate chat history and rerun
                msg = {"role": "assistant", "content": response_text}
                if "current_slot_id" in st.session_state and st.session_state.get("booking_history") is not None:
                    st.session_state.booking_history.append(msg)
                if st.session_state.get("post_ctx") is not None and st.session_state.get("post_history") is not None:
                    st.session_state.post_history.append(msg)
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
            content = msg.get("content")
            if msg["role"] == "assistant":
                if isinstance(content, (str, dict)):
                    render_json_response_block(content)
            else:
                if isinstance(content, str):
                    st.markdown(content)

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
            response_text = _prepare_response_content(result.get("data", {}))

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
                response_text = _prepare_response_content(result.get("data", {}))
                st.session_state.booking_history.append({"role": "assistant", "content": response_text})
                st.rerun()
            else:
                st.error(result.get("error", "Unknown error"))

        # Render history
        for idx, msg in enumerate(st.session_state.booking_history):
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    content = msg.get("content")
                    if isinstance(content, (str, dict)):
                        # Try MCQ render; if not MCQ, show rich JSON
                        if not render_mcq_if_present(content, key_prefix=f"book_hist_{idx}", slot_id=st.session_state.current_slot_id):
                            render_json_response_block(content)
                else:
                    content = msg.get("content")
                    if isinstance(content, str):
                        st.markdown(content)

        # If last assistant message is MCQ, or booking is marked complete (status=="end"), disable free input
        show_free_input = True
        if st.session_state.booking_history:
            try:
                last = st.session_state.booking_history[-1]
                parsed = (
                    _normalize_nested_json(last["content"])
                    if last["role"] == "assistant"
                    else None
                )
                if isinstance(parsed, dict):
                    if parsed.get("question_type") == "mcq":
                        show_free_input = False
                    progress = parsed.get("assessment_progress") or parsed.get("status")
                    if isinstance(progress, str) and progress.lower() in {"end", "complete", "completed"}:
                        show_free_input = False
                        st.success("Pre-consultation is complete. Summary has been saved.")
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
                    response_text = _prepare_response_content(result.get("data", {}))
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
            # Normalize nested response formats (stringified JSON, answer/response nesting)
            parsed = _normalize_nested_json(data.get("response", {}))
            if not isinstance(parsed, dict) or not parsed.get("processed_files"):
                parsed = _normalize_nested_json(data.get("answer", {}))
            if not isinstance(parsed, dict) or not parsed.get("processed_files"):
                parsed = _normalize_nested_json(data)

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
                        if info.get("doc_type"):
                            st.caption(f"Doc Type: {info.get('doc_type')}")
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
                # Fallback to raw display
                raw_text = data.get("response") or data.get("answer") or "{}"
                st.markdown("### Processing Result")
                st.text_area("Result", raw_text, height=200, disabled=True, label_visibility="collapsed")


def _render_treatment_plan(plan_items):
    if not isinstance(plan_items, list):
        return
    for i, item in enumerate(plan_items, 1):
        st.markdown(f"### Plan {i}: {item.get('service', 'Treatment')}")
        specs_text = item.get("specifications_text")
        specs = item.get("specifications")
        if specs_text:
            st.caption(specs_text)
        if isinstance(specs, dict) and specs:
            with st.expander("Specifications"):
                for k, v in specs.items():
                    st.markdown(f"- **{k}**: {v}")
        if item.get("rationale"):
            st.markdown("**Rationale**")
            st.markdown(item["rationale"])
        if isinstance(item.get("steps"), list) and item["steps"]:
            st.markdown("**Steps**")
            for step in item["steps"]:
                st.markdown(f"- {step}")
        if item.get("estimated_sessions") is not None:
            st.caption(f"Estimated sessions: {item.get('estimated_sessions')}")
        if item.get("follow_up"):
            st.caption(f"Follow-up: {item.get('follow_up')}")
        if isinstance(item.get("buttons"), list) and item["buttons"]:
            cols = st.columns(min(3, len(item["buttons"])))
            for idx_btn, btn in enumerate(item["buttons"][:3]):
                with cols[idx_btn]:
                    st.button(btn.get("label", "Action"), use_container_width=True, key=f"tp_btn_{i}_{idx_btn}")
        if i < len(plan_items):
            st.markdown("---")


def post_consultation_mode():
    st.subheader("Post Consultation")
    st.markdown("Provide Slot ID and post consultation text (doctor's notes).")

    col1, col2 = st.columns([3, 1])
    with col1:
        slot_id = st.text_input("Slot ID", placeholder="e.g., slot_123", key="post_slot_id")
    with col2:
        submit = st.button("Process", type="primary", use_container_width=True)

    post_text = st.text_area("Post Consultation Text", height=160, placeholder="e.g., 1500 grafts, frontal area, FUE. Consider contour refinement ...")

    # Initialize chat state for post-consultation
    if "post_history" not in st.session_state:
        st.session_state.post_history = []
    if "post_ctx" not in st.session_state:
        st.session_state.post_ctx = None

    if submit:
        if not slot_id or not post_text.strip():
            st.warning("Please enter both Slot ID and Post Consultation Text.")
            return
        # Save context for chat; do NOT call API yet. Chat input will trigger first call.
        st.session_state.post_ctx = {"slot_id": slot_id, "post_text": post_text}
        st.session_state.post_history = []
        st.success("Context saved. You can now chat to generate or refine the treatment plan.")

    # If context set, render chat-style interface
    if st.session_state.post_ctx:
        st.info(f"Current Slot ID: {st.session_state.post_ctx['slot_id']}")

        chat_container = st.container()
        with chat_container:
            for idx, msg in enumerate(st.session_state.post_history):
                with st.chat_message(msg["role"]):
                    content = msg.get("content")
                    if msg["role"] == "assistant":
                        # Render answer and treatment plan
                        handled_mcq = False
                        if isinstance(content, (str, dict)):
                            handled_mcq = render_mcq_if_present(
                                content,
                                key_prefix=f"post_hist_{idx}",
                                slot_id=st.session_state.post_ctx["slot_id"],
                            )
                        if not handled_mcq:
                            parsed = _normalize_nested_json(content)
                            if isinstance(parsed, dict):
                                ans = parsed.get("answer")
                                if isinstance(ans, str) and ans.strip():
                                    st.markdown(ans)
                                plan = parsed.get("treatment_plan")
                                if plan:
                                    st.markdown("---")
                                    st.markdown("## Treatment Plan")
                                    _render_treatment_plan(plan)
                                if parsed.get("additional_recommendations"):
                                    st.markdown("#### Additional Recommendations")
                                    for rec in parsed.get("additional_recommendations", []):
                                        st.markdown(f"- {rec}")
                                if parsed.get("warnings"):
                                    st.markdown("#### Warnings")
                                    for w in parsed.get("warnings", []):
                                        st.markdown(f"- {w}")
                                if isinstance(parsed.get("products"), list) and parsed.get("products"):
                                    st.markdown("---")
                                    with st.expander("Products", expanded=True):
                                        for product in parsed.get("products", []):
                                            st.markdown(f"- {product}")
                                if isinstance(parsed.get("lab_tests"), list) and parsed.get("lab_tests"):
                                    st.markdown("---")
                                    with st.expander("Lab Tests", expanded=True):
                                        for test in parsed.get("lab_tests", []):
                                            st.markdown(f"- {test}")
                                # Show full JSON for debugging/inspection
                                with st.expander("Raw JSON"):
                                    st.json(parsed)
                            elif isinstance(content, str):
                                st.markdown(content)
                    else:
                        if isinstance(content, str):
                            st.markdown(content)

        # Chat input for follow-ups
        user_msg = st.chat_input("Ask follow-up or refine plan...")
        if user_msg:
            st.session_state.post_history.append({"role": "user", "content": user_msg})
            with st.chat_message("user"):
                st.markdown(user_msg)

            ctx = st.session_state.post_ctx
            payload = {
                "session_id": st.session_state.session_id,
                "user_id": st.session_state.user_id,
                "slot_id": ctx["slot_id"],
                "post_consultation_text": ctx["post_text"],
                "input": user_msg,
            }
            with st.spinner("Processing..."):
                result = make_api_request(payload)

            if result.get("success"):
                response_text = _prepare_response_content(result.get("data", {}))
                st.session_state.post_history.append({"role": "assistant", "content": response_text})
                st.rerun()
            else:
                st.error(result.get("error", "Unknown error"))


def main():
    # Initialize IDs once; do not change across inputs
    ensure_ids_once()

    st.title("🏥 Doctor Recommendation System (Deployed)")
    st.markdown("---")

    # On-page mode buttons (Ask, Booking Chat, Upload)
    if "dep_selected_mode" not in st.session_state:
        st.session_state.dep_selected_mode = "Ask"

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("💬 Ask", use_container_width=True):
            st.session_state.dep_selected_mode = "Ask"
    with b2:
        if st.button("📅 Booking Chat", use_container_width=True):
            st.session_state.dep_selected_mode = "Booking Chat"
    with b3:
        if st.button("📤 Upload (URLs)", use_container_width=True):
            st.session_state.dep_selected_mode = "Upload"
    with b4:
        if st.button("📝 Post Consultation", use_container_width=True):
            st.session_state.dep_selected_mode = "Post"

    # IDs panel with refresh button
    c_sid, c_btn = st.columns([0.8, 0.2])
    with c_sid:
        st.caption(f"Session ID: {st.session_state.session_id}")
        st.caption(f"User ID: {st.session_state.user_id}")
    with c_btn:
        if st.button("🔄 New Session", use_container_width=True):
            reset_session_ids_and_state()

    st.markdown("---")

    if st.session_state.dep_selected_mode == "Ask":
        ask_mode()
    elif st.session_state.dep_selected_mode == "Booking Chat":
        booking_chat_mode()
    elif st.session_state.dep_selected_mode == "Upload":
        upload_urls_mode()
    elif st.session_state.dep_selected_mode == "Post":
        post_consultation_mode()


if __name__ == "__main__":
    main()
