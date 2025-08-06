from flaskr import create_app, db
from flaskr.models import ModuleData, CellData

def clear_moduledata():
    app = create_app()  # or however you create your Flask app
    with app.app_context():
        # Delete all rows from ModuleData
        db.session.query(CellData).delete()
        db.session.commit()
        print("ModuleData table cleared.")

if __name__ == "__main__":
    clear_moduledata()
