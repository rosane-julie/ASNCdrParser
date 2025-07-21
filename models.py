from app import db
from datetime import datetime
import json

class CDRFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    parse_status = db.Column(db.String(50), default='pending')  # pending, success, error
    error_message = db.Column(db.Text)
    records_count = db.Column(db.Integer, default=0)
    parse_offset = db.Column(db.Integer, default=0)
    
    # Relationship to parsed records
    records = db.relationship('CDRRecord', backref='file', lazy=True, cascade='all, delete-orphan')

class CDRRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('cdr_file.id'), nullable=False)
    record_index = db.Column(db.Integer, nullable=False)
    record_type = db.Column(db.String(100))
    calling_number = db.Column(db.String(50))
    called_number = db.Column(db.String(50))
    call_duration = db.Column(db.Integer)  # in seconds
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    raw_data = db.Column(db.Text)  # JSON string of the complete parsed record
    
    def get_raw_data(self):
        """Return the raw data as a Python object"""
        if self.raw_data:
            try:
                return json.loads(self.raw_data)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_raw_data(self, data):
        """Set the raw data from a Python object"""
        self.raw_data = json.dumps(data, default=str, indent=2)
