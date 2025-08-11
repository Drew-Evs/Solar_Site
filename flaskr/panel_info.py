from flask import Blueprint, render_template, request, session, url_for, jsonify
from .models import PanelInfo
from sqlalchemy import and_
from .classes import Solar_Cell, Panel
from . import db

pi = Blueprint('panel_info', __name__)

@pi.route('/filter_data', methods=['GET', 'POST'])
def filter_data():
    print("filter running")

    return jsonify({"status": "success"})


@pi.route('/build_data', methods=['POST'])
def build_data():
    print("This is running")

    #get the filters
    panel_name = request.form.get("panel_name", None)

    def try_float(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    power_input = try_float(request.form.get("power_input", None))
    width_input = try_float(request.form.get("width_input", None))
    height_input = try_float(request.form.get("height_input", None))

    query = PanelInfo.query

    #add filters to the list
    filters = []

    if panel_name:
        #contains substring
        filters.append(PanelInfo.panel_name.ilike(f'%{panel_name}%'))

    #tolerance for numbers 
    tolerance = 0.1 #10% tolerance

    if power_input is not None:
        low = power_input * (1 - tolerance)
        high = power_input * (1 + tolerance)
        filters.append(PanelInfo.max_power.between(low, high))

    if width_input is not None:
        low = width_input * (1 - tolerance)
        high = width_input * (1 + tolerance)
        filters.append(PanelInfo.width.between(low, high))

    if height_input is not None:
        low = height_input * (1 - tolerance)
        high = height_input * (1 + tolerance)
        filters.append(PanelInfo.length.between(low, high))

    if filters:
        query = query.filter(and_(*filters))

    panels = query.distinct().all()

    panel_info = [
        {'name':p.panel_name, 'length':p.length, 'width':p.width, 'cells':p.num_cells, 'power':p.max_power}
        for p in panels
    ]

    return jsonify(panel_info)

@pi.route('/calc_power', methods=['POST'])
def calc_power():
    panel_name = request.form.get("panel_name")

    panel = PanelInfo.query.filter_by(panel_name=panel_name).first()

    test_cell = Solar_Cell(None, panel_name, 950, 25)
    initial_conditions = test_cell.ACTUAL_CONDITIONS[:5]
    test_panel = Panel(initial_conditions, panel_name=panel_name, module_count=panel.num_diodes,
        cell_per_module=(panel.num_cells//panel.num_diodes))

    pmax, vmp, imp = test_panel.model_power()
    panel.max_power = pmax

    db.session.commit()

    return jsonify({'power': pmax})

