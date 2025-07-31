from flask import Blueprint, render_template, request, session, url_for
from .models import PanelInfo

pi = Blueprint('panel_info', __name__)

@pi.route('/generate_panel', methods=['GET', 'POST'])
def generate_panel():

    panels = PanelInfo.query.with_entities(PanelInfo.panel_name).distinct().all()
    panel_names = [p.panel_name for p in panels]
    
    #test if its get or post
    if request.method == 'POST':
        try:
            panel_name = request.form.get("panel_name", None)
            if panel_name is None:
                raise ValueError

            record = PanelInfo.query.filter_by(
                panel_name=panel_name
            ).first()

            if not record: raise ValueError(f'Panel {panel_name} not found')

            Ns = record.num_cells
            num_rows = Ns//6

            return render_template('panel_page.html', panel_names=panel_names,
                num_rows=num_rows, panel_name=panel_name)

        except ValueError as e:
            print(f'Error: {e}')
            return render_template('panel_page.html', 
                                    panel_names=panel_names,
                                    error=str(e))

    return render_template('panel_page.html', panel_names=panel_names)