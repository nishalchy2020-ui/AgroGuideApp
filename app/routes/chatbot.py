import json
import logging

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context
from flask_login import current_user, login_required

from app import db
from app.models import ChatbotMessage
from app.services.chatbot_service import generate_hybrid_reply, generate_hybrid_reply_stream
from app.services.history_service import log_activity
from app.services.user_context import chatbot_user_context

chatbot_bp = Blueprint("chatbot", __name__)
logger = logging.getLogger("agroguide.chatbot")


@chatbot_bp.route("/")
@login_required
def index():
    messages = (
        ChatbotMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatbotMessage.created_at.asc())
        .limit(50)
        .all()
    )
    search_configured = current_app.config.get("SEARCH_API_KEY", "").strip() != ""
    return render_template(
        "chatbot/index.html",
        messages=messages,
        search_configured=search_configured,
        search_provider=current_app.config.get("SEARCH_PROVIDER", "tavily"),
    )


@chatbot_bp.route("/message", methods=["POST"])
@login_required
def message():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or request.form.get("message", "")).strip()

    if not text:
        return jsonify({"error": "Empty message"}), 400

    prior = (
        ChatbotMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatbotMessage.created_at.desc())
        .limit(10)
        .all()
    )
    prior.reverse()
    conversation = [{"role": m.role, "content": m.display_message} for m in prior]

    user_context = chatbot_user_context(current_user.id)
    result = generate_hybrid_reply(
        text,
        conversation=conversation,
        user_context=user_context,
    )
    reply = result["reply"]
    source_type = result.get("source_type", "fallback")

    user_msg = ChatbotMessage(
        user_id=current_user.id,
        role="user",
        content=text,
        message=text,
        source_type="local",
    )
    assistant_msg = ChatbotMessage(
        user_id=current_user.id,
        role="assistant",
        content=reply,
        message=reply,
        source_type=source_type,
        sources=json.dumps(result.get("sources", [])),
    )
    db.session.add(user_msg)
    db.session.add(assistant_msg)
    log_activity(
        current_user.id,
        "chatbot",
        f"Chat: {text[:60]}{'...' if len(text) > 60 else ''}",
        {
            "question": text,
            "answer_preview": reply[:200],
            "context_used": bool(user_context.get("summary")),
        },
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to save chatbot conversation for user_id=%s", current_user.id)
        return jsonify({"error": "Message could not be saved. Please retry."}), 500

    return jsonify(
        {
            "reply": reply,
            "error": bool(result.get("error")),
            "source_type": source_type,
            "sources": result.get("sources", []),
            "context_used": bool(user_context.get("summary")),
            "user_message_id": user_msg.id,
            "assistant_message_id": assistant_msg.id,
        }
    )


@chatbot_bp.route("/message/stream", methods=["POST"])
@login_required
def stream_message():
    """Stream Server-Sent Events while generating and persist the final conversation."""
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or request.form.get("message", "")).strip()
    if not text:
        return jsonify({"error": "Empty message"}), 400

    user_id = current_user.id
    prior = (
        ChatbotMessage.query.filter_by(user_id=user_id)
        .order_by(ChatbotMessage.created_at.desc())
        .limit(10)
        .all()
    )
    prior.reverse()
    conversation = [{"role": item.role, "content": item.display_message} for item in prior]
    user_context = chatbot_user_context(user_id)

    def encode_event(event):
        return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    @stream_with_context
    def generate_events():
        result = None
        try:
            # Flush response headers before retrieval/model work begins.
            yield encode_event({"type": "ready"})
            for event in generate_hybrid_reply_stream(
                text,
                conversation=conversation,
                user_context=user_context,
            ):
                if event["type"] == "chunk":
                    yield encode_event(event)
                elif event["type"] == "result":
                    result = event["result"]

            if not result:
                raise RuntimeError("The chatbot stream ended without a result.")

            reply = result["reply"]
            source_type = result.get("source_type", "fallback")
            user_msg = ChatbotMessage(
                user_id=user_id,
                role="user",
                content=text,
                message=text,
                source_type="local",
            )
            assistant_msg = ChatbotMessage(
                user_id=user_id,
                role="assistant",
                content=reply,
                message=reply,
                source_type=source_type,
                sources=json.dumps(result.get("sources", [])),
            )
            db.session.add(user_msg)
            db.session.add(assistant_msg)
            log_activity(
                user_id,
                "chatbot",
                f"Chat: {text[:60]}{'...' if len(text) > 60 else ''}",
                {
                    "question": text,
                    "answer_preview": reply[:200],
                    "context_used": bool(user_context.get("summary")),
                },
            )
            db.session.commit()

            yield encode_event(
                {
                    "type": "done",
                    "source_type": source_type,
                    "sources": result.get("sources", []),
                    "error": bool(result.get("error")),
                    "user_message_id": user_msg.id,
                    "assistant_message_id": assistant_msg.id,
                }
            )
        except Exception:
            db.session.rollback()
            logger.exception("Failed to stream chatbot response for user_id=%s", user_id)
            yield encode_event(
                {
                    "type": "error",
                    "message": "The response could not be completed. Please try again.",
                }
            )

    return Response(
        generate_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


@chatbot_bp.route("/send", methods=["POST"])
@login_required
def send():
    """Backward-compatible alias for /message."""
    return message()


@chatbot_bp.route("/delete/<int:message_id>", methods=["POST"])
@login_required
def delete(message_id):
    msg = ChatbotMessage.query.filter_by(
        id=message_id,
        user_id=current_user.id,
    ).first_or_404()
    try:
        db.session.delete(msg)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to delete chatbot message id=%s", message_id)
        return jsonify({"error": "Message could not be deleted."}), 500
    return jsonify({"ok": True, "deleted_id": message_id})


@chatbot_bp.route("/clear", methods=["POST"])
@login_required
def clear():
    try:
        ChatbotMessage.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to clear chatbot messages for user_id=%s", current_user.id)
        return jsonify({"error": "Messages could not be cleared."}), 500
    return jsonify({"ok": True})
