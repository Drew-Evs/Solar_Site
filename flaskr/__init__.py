import os

from flask import Flask

#creates the app
def create_app(test_config=None):
    #creates then configures
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

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

    from . import routes
    app.register_blueprint(routes.db)

    from . import cell_info
    app.register_blueprint(cell_info.ci)

    return app