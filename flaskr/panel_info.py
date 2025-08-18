from flask import Blueprint, render_template, request, session, url_for, jsonify
from .models import PanelInfo, CustomPanel
from sqlalchemy import and_
from .classes import Solar_Cell, Panel
from . import db
import math 
import flaskr.helper_functions as hp

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

#takes in inputs from a reference sheet to build a custom new panel
#also needs to be added to the panel_info table
@pi.route('/new_panel', methods=['POST'])
def new_panel():
    panel_name = request.form.get("panel_name") or None
    panel_length = float(request.form.get("panel_length" or math.nan))
    panel_width = float(request.form.get("panel_width" or math.nan))
    num_cells = int(request.form.get("num_cells" or math.nan))
    noct = float(request.form.get("noct" or math.nan))
    num_diodes = int(request.form.get("num_diodes" or math.nan))

    alpha_sc = float(request.form.get("alpha_sc" or math.nan))
    Voc = float(request.form.get("Voc", math.nan))
    Isc = float(request.form.get("Isc", math.nan))
    Vmp = float(request.form.get("Vmp", math.nan))
    Imp = float(request.form.get("Imp", math.nan))
    panel_type = request.form.get("panel_type")
    gamma_pmp = float(request.form.get("gamma_pmp", math.nan))
    beta_voc = float(request.form.get("beta_voc", math.nan))

    #check all valid inputs
    if any(math.isnan(val) for val in [
        alpha_sc, Voc, Isc, Vmp, Imp,
        panel_length, panel_width, num_cells, noct, num_diodes
    ]) or panel_name is None:
        return jsonify({'status': 'error', 'message': 'One or more fields are NaN'})

    existing_panel_info = PanelInfo.query.filter_by(
        panel_name=panel_name
    ).first()

    existing_panel_custom = CustomPanel.query.filter_by(
        panel_name=panel_name
    ).first()

    if existing_panel_info or existing_panel_custom:
        return jsonify({'status': 'error', 'message': 'Already exists in the database'})

    try:
        i_l_ref, i_o_ref, r_s, r_sh_ref, a_ref, alpha_sc = hp.param_extraction(Voc, Isc, Vmp, Imp, 
                                                    num_cells, alpha_sc, beta_voc, gamma_pmp, panel_type)
    except Exception as e:
        print(f"failed due to {e}")
        pass

    # expected ideal Pmp
    expected_pmp = Vmp * Imp
    print(f"\nExpected Pmp = Vmp * Imp = {Vmp} * {Imp} = {expected_pmp:.1f} W")
    print(f"\n Alpha sc is {alpha_sc}")

    new_custom_record = CustomPanel(
        panel_name = panel_name,
        alpha_sc = alpha_sc,
        a_ref = a_ref,
        i_l_ref = i_l_ref,
        i_o_ref = i_o_ref,
        r_sh_ref = r_sh_ref,
        r_s = r_s,
        num_cells = num_cells
    )

    db.session.add(new_custom_record)
    db.session.commit()

    pmax, vmp, imp = hp.calculate_pmp_simple(i_l_ref, i_o_ref, r_s, r_sh_ref, a_ref, alpha_sc=alpha_sc)

    new_panel_record = PanelInfo(
        panel_name=panel_name,
        length=panel_length,
        width=panel_width,
        num_cells=num_cells,
        num_diodes=num_diodes,
        max_power=pmax,
        noct=noct
    )

    print(f"\nMeasured/Modelled Pmp = {pmax} W")
    print(f"Ratio measured/expected = {pmax/expected_pmp:.3f}")

    db.session.add(new_panel_record)
    db.session.commit()

    return jsonify({'status': 'success'})


    




