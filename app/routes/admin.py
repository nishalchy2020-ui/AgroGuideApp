from collections import Counter

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import AdminLog, DiseaseKnowledge, ScanResult, User
from app.utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    total_scans = ScanResult.query.count()
    recent_scans = ScanResult.query.order_by(ScanResult.created_at.desc()).limit(10).all()

    disease_counts = Counter(
        s.disease_class for s in ScanResult.query.with_entities(ScanResult.disease_class).all()
    )
    top_diseases = disease_counts.most_common(8)

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_scans=total_scans,
        recent_scans=recent_scans,
        top_diseases=top_diseases,
    )


@admin_bp.route("/knowledge", methods=["GET", "POST"])
@login_required
@admin_required
def knowledge():
    if request.method == "POST":
        class_name = request.form.get("class_name", "").strip()
        record = DiseaseKnowledge.query.filter_by(class_name=class_name).first()
        if not record:
            flash("Class not found.", "error")
        else:
            record.description = request.form.get("description", "")
            record.symptoms = request.form.get("symptoms", "")
            record.causes = request.form.get("causes", "")
            record.treatment = request.form.get("treatment", "")
            record.prevention = request.form.get("prevention", "")
            record.severity = request.form.get("severity", "medium")
            record.pesticide = request.form.get("pesticide", "")
            record.organic_solution = request.form.get("organic_solution", "")
            db.session.add(
                AdminLog(
                    admin_id=current_user.id,
                    action="update_knowledge",
                    details=class_name,
                )
            )
            db.session.commit()
            flash("Knowledge base updated.", "success")
            return redirect(url_for("admin.knowledge", edit=class_name))

    edit_class = request.args.get("edit")
    records = DiseaseKnowledge.query.order_by(DiseaseKnowledge.class_name).all()
    edit_record = None
    if edit_class:
        edit_record = DiseaseKnowledge.query.filter_by(class_name=edit_class).first()

    return render_template(
        "admin/knowledge.html",
        records=records,
        edit_record=edit_record,
    )


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)
