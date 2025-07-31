from flask import Blueprint, render_template, request, session, url_for
from .models import PanelInfo

bp = Blueprint('routes', __name__)

@bp.route('/')
def dashboard():
    return render_template('dashboard.html')

@bp.route('/cell')
def cell():
    panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
    panel_names = [p.panel_name for p in panels]
    return render_template('cell_page.html', panel_names=panel_names)

@bp.route('/panel')
def panel():
    panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
    panel_names = [p.panel_name for p in panels]
    return render_template('panel_page.html', panel_names=panel_names, num_rows=0)

@bp.route('/string')
def string():
    panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
    panel_names = [p.panel_name for p in panels]
    return render_template('string_page.html', panel_names=panel_names)