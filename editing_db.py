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

def add_noct():
    app = create_app()
    with app.app_context():
        cec_modules = pvlib.pvsystem.retrieve_sam('CECMod')
        print(cec_modules.index) 

        for name in cec_modules:
            module = cec_modules[name]

            noct = module['T_NOCT']

            record = PanelInfo.query.filter_by(
                panel_name=name
            ).first()
            record.noct = noct

            print(f'To {name} added noct: {noct}')
        
        db.session.commit()

def clear_custom_and_panelinfo():
    from flaskr import create_app, db
    from flaskr.models import PanelInfo, CustomPanel, ModuleLookup  # adjust imports to your actual models

    app = create_app()
    with app.app_context():
        # --- 1. Clear all entries in custom_panel ---
        deleted_custom = db.session.query(CustomPanel).delete()
        print(f"Deleted {deleted_custom} rows from CustomPanel")

        # --- 2. Delete PanelInfo entries with id >= 21536 ---
        deleted_panelinfo = db.session.query(PanelInfo).filter(PanelInfo.id >= 21536).delete()
        print(f"Deleted {deleted_panelinfo} rows from PanelInfo (id >= 21536)")

        deleted_lookup = db.session.query(ModuleLookup).delete()
        print(f"Deleted {deleted_lookup} rows from CustomPanel")

        # Commit changes
        db.session.commit()
        print("Database cleanup complete.")

def clear_whole_mod_lookup():
    from flaskr import create_app, db
    from flaskr.models import WholeModuleLookup  # adjust imports to your actual models

    app = create_app()
    with app.app_context():
        # --- 1. Clear all entries in custom_panel ---
        deleted_custom = db.session.query(WholeModuleLookup).delete()
        print(f"Deleted {deleted_custom} rows from WholeModuleLookup")

if __name__ == "__main__":
   clear_custom_and_panelinfo()