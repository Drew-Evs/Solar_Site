from flask import Blueprint, render_template, request, session, url_for
from .classes import Solar_Cell
import flaskr.helper_functions as hp
import os
from .models import PanelInfo
ci = Blueprint('cell_info', __name__)

@ci.route('/generate_cell_graphs', methods=['GET', 'POST'])
def generate_cell_graphs():
    try:
        #request info
        temp = float(request.form.get("temperature", 25))
        irr = float(request.form.get("irradiance", 950))
        panel_name = request.form.get("panel_name", "Jinko_Solar_Co___Ltd_JKM410M_72HL_V")

        out_paths = []
        plot_dir = f'flaskr/static/plots/{panel_name}'

        if request.method == 'POST':
            cell = Solar_Cell(initial_conditions=None, panel_name=panel_name,
                shadow=irr, temp=temp)
            Pmax, Vmp, Imp = [hp.round_sf(x, 3) for x in cell.model_power(True)]
            Voc, Isc = [hp.round_sf(x, 3) for x in cell.find_isc_voc()]
            Iph, Is, n, Rs, Rp, Kt = [hp.round_sf(x, 3) for x in cell.get_params()]

        #finds path relative to panel name
        if os.path.exists(plot_dir):
            for fname in os.listdir(plot_dir):
                if fname.endswith('.png'):
                    out_paths.append(f'plots/{panel_name}/{fname}')

        panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
        panel_names = [p.panel_name for p in panels]

        return render_template('cell_page.html', graphs=out_paths,
            temperature=temp, irradiance=irr, panel_name=panel_name,
            voc=Voc, isc=Isc, pmax=Pmax, vmp=Vmp, imp=Imp,
            iph=Iph, isat=Is, n=n, rs=Rs, rp=Rp, panel_names=panel_names)

    except Exception as e:
        print(f'Failed due to {e}')



