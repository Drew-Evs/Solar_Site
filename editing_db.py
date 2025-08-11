from flaskr import create_app, db
from flaskr.models import PanelInfo
from flaskr import classes
import difflib
import pvlib

def clear_moduledata():
    app = create_app()
    with app.app_context():
        panels = PanelInfo.query.all()

        processed = []

        for p in panels:
            # Skip if too similar to already processed
            if all(difflib.SequenceMatcher(None, p.panel_name, x).ratio() < 0.8 for x in processed):
                # Create test cell to get conditions (or replace with pvlib inputs directly)
                test_cell = classes.Solar_Cell(None, p.panel_name, 950, 25)
                initial_conditions = test_cell.ACTUAL_CONDITIONS
                print(f'Init conditions: {initial_conditions}')

                # Extract params for pvlib singlediode:
                # You will need to adapt these based on your data and initial_conditions structure
                photocurrent = initial_conditions[0]  # example placeholder
                saturation_current = initial_conditions[1]  # example placeholder
                resistance_series = initial_conditions[3]  # example placeholder
                resistance_shunt = initial_conditions[4]  # example placeholder
                nNsVth = initial_conditions[3]*p.num_cells * ((298.15 *  1.380649e-23)/1.602176634e-19)  # example placeholder

                # Run pvlib singlediode model
                sd_result = pvlib.pvsystem.singlediode(
                    photocurrent=photocurrent,
                    saturation_current=saturation_current,
                    resistance_series=resistance_series,
                    resistance_shunt=resistance_shunt,
                    nNsVth=nNsVth,
                )

                pmax = sd_result['p_mp']  # max power from pvlib model

                # Update panel max_power field
                p.max_power = pmax*p.num_cells
                print(f"{p.panel_name} max power set to {pmax}")

                processed.append(p.panel_name)

        db.session.commit()


if __name__ == "__main__":
    clear_moduledata()