import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

#creates the app
def create_app(test_config=None):
    #creates then configures
    app = Flask(__name__, instance_relative_config=True)

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    clear_uploads_folder(app)

    db.init_app(app)
    migrate.init_app(app, db)

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        #load the test configuration if its passed in
        app.config.from_mapping(test_config)

    #makes sure the folder holding instance exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import routes, models
    app.register_blueprint(routes.bp)

    with app.app_context():
        db.create_all()

    from . import cell_info
    app.register_blueprint(cell_info.ci)

    from . import panel_info
    app.register_blueprint(panel_info.pi)

    from . import string_modelling
    app.register_blueprint(string_modelling.sm)

    return app

#clears the uploads folder when started
def clear_uploads_folder(app):
    uploads_path = os.path.join(app.root_path, 'static/uploads')
    if os.path.exists(uploads_path):
        for filename in os.listdir(uploads_path):
            file_path = os.path.join(uploads_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path} due to {e}')