from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db
from app.models import ChatbotMessage
from app.services.chatbot_service import generate_hybrid_reply
from app.services.history_service import log_activity

chatbot_bp = Blueprint("chatbot", __name__)


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

    result = generate_hybrid_reply(text, conversation=conversation)
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
    )
    db.session.add(user_msg)
    db.session.add(assistant_msg)
    log_activity(
        current_user.id,
        "chatbot",
        f"Chat: {text[:60]}{'...' if len(text) > 60 else ''}",
        {"question": text, "answer_preview": reply[:200]},
    )
    db.session.commit()

    return jsonify(
        {
            "reply": reply,
            "error": bool(result.get("error")),
            "source_type": source_type,
            "sources": result.get("sources", []),
            "user_message_id": user_msg.id,
            "assistant_message_id": assistant_msg.id,
        }
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
    db.session.delete(msg)
    db.session.commit()
    return jsonify({"ok": True, "deleted_id": message_id})


@chatbot_bp.route("/clear", methods=["POST"])
@login_required
def clear():
    ChatbotMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})
