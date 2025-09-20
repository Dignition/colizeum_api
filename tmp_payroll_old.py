# -*- coding: utf-8 -*-

from flask import Blueprint, render_template
from flask_login import login_required
bp = Blueprint("payroll", __name__, template_folder="../../templates/payroll")

@bp.route("/")
@login_required
def index():
    return render_template("payroll/index.html", page_title="Зарплата")

