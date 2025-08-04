from . import db

class CellData(db.Model):
    __tablename__ = 'cell_data'

    id = db.Column(db.Integer, primary_key=True)
    panel_name = db.Column(db.String(200))
    temperature = db.Column(db.Integer)
    irradiance = db.Column(db.Integer)
    iph = db.Column(db.Float)
    isat = db.Column(db.Float)
    n = db.Column(db.Float)
    Rs = db.Column(db.Float)
    Rp = db.Column(db.Float)

    voc = db.Column(db.Float, nullable=True)
    isc = db.Column(db.Float, nullable=True)
    vmp = db.Column(db.Float, nullable=True)
    imp = db.Column(db.Float, nullable=True)
    pmax = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.Index('idx_cell_lookup', 'panel_name', 'temperature', 'irradiance'),
    )



class PanelInfo(db.Model):
    __tablename__ = 'panel_info'

    id = db.Column(db.Integer, primary_key=True)
    panel_name = db.Column(db.String(200))
    length = db.Column(db.Float)
    width = db.Column(db.Float)
    num_cells = db.Column(db.Integer)
    num_diodes = db.Column(db.Integer)


class EnvironmentalData(db.Model):
    __tablename__ = 'envir_info'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime)
    hour = db.Column(db.Integer)
    longitude = db.Column(db.Float)
    latitude = db.Column(db.Float)
    temperature = db.Column(db.Float)
    irradiance = db.Column(db.Float)


class ModuleData(db.Model):
    __tablename__ = "module_data"

    id = db.Column(db.Integer, primary_key=True)
    kt = db.Column(db.Float, nullable=False)
    iph = db.Column(db.Float, nullable=False)
    isat = db.Column(db.Float, nullable=False)
    n = db.Column(db.Float, nullable=False)
    Rs = db.Column(db.Float, nullable=False)
    Rp = db.Column(db.Float, nullable=False)

    voltage = db.Column(db.Float, nullable=False)
    current = db.Column(db.Float, nullable=False)

    #indexing for speed
    __table_args__ = (
        db.Index('idx_voltage_lookup', 'kt', 'iph', 'isat', 'n', 'Rs', 'Rp', 'current'),
    )

