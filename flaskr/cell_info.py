from flask import Blueprint, render_template, request, session, url_for
from .classes import Solar_Cell
import flaskr.helper_functions as hp
import os

ci = Blueprint('cell_info', __name__)

@ci.route('/cell', methods=['GET', 'POST'])
def generate_cell_graphs(panel_name='Jinko_Solar_Co___Ltd_JKM410M_72HL_V'):
    #generates/finds hash tables
    c_hash_db = hp.create_hash_c(panel_name)

    out_paths = []
    plot_dir = f'flaskr/static/plots/{panel_name}'

    if request.method == 'POST':
        cell = Solar_Cell(initial_conditions=None, panel_name=panel_name,
            shadow=950, temp=25, c_hash_db=c_hash_db)
        cell.model_power(True)

    #finds path relative to panel name
    if os.path.exists(plot_dir):
        for fname in os.listdir(plot_dir):
            if fname.endswith('.png'):
                out_paths.append(f'plots/{panel_name}/{fname}')

    return render_template('cell_page.html', graphs=out_paths)