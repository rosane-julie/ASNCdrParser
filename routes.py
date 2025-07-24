import os
import json
import logging
from datetime import datetime
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
)
from werkzeug.utils import secure_filename
from app import app, db
from models import CDRFile, CDRRecord
from cdr_parser import CDRParser
import shutil
import csv
import io

ALLOWED_EXTENSIONS = {"dat", "cdr", "bin", "asn1", "ber", "der"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    # Get recent files
    recent_files = CDRFile.query.order_by(CDRFile.upload_time.desc()).limit(10).all()
    return render_template("index.html", recent_files=recent_files)


@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        # Check if file was uploaded
        if "file" not in request.files:
            flash("No file selected", "error")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                # Secure the filename
                original_filename = file.filename
                filename = secure_filename(file.filename)

                # Save the file
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)

                # Get file size
                file_size = os.path.getsize(filepath)

                # Create database record
                cdr_file = CDRFile(
                    filename=filename,
                    original_filename=original_filename,
                    file_size=file_size,
                )
                db.session.add(cdr_file)
                db.session.commit()

                # Parse the first chunk of the file for faster feedback
                parser = CDRParser()
                try:
                    records, reached_end, new_offset = parser.parse_file_chunk(
                        filepath,
                        max_records=100,
                    )

                    # Save parsed records to database
                    for i, record in enumerate(records):
                        cdr_record = CDRRecord(
                            file_id=cdr_file.id,
                            record_index=i,
                            record_type=record.get("record_type", "unknown"),
                            calling_number=record.get("calling_number"),
                            called_number=record.get("called_number"),
                            call_duration=record.get("call_duration"),
                            start_time=record.get("start_time"),
                            end_time=record.get("end_time"),
                        )
                        cdr_record.set_raw_data(record)
                        db.session.add(cdr_record)

                    cdr_file.records_count = len(records)
                    cdr_file.parse_status = "success"
                    cdr_file.parse_offset = new_offset
                    db.session.commit()

                    flash(
                        f"File uploaded. Parsed {len(records)} records.",
                        "success",
                    )
                    return redirect(url_for("view_results", file_id=cdr_file.id))

                except Exception as e:
                    logging.error(f"Error parsing file {filename}: {str(e)}")
                    cdr_file.parse_status = "error"
                    cdr_file.error_message = str(e)
                    db.session.commit()
                    flash(f"Error parsing file: {str(e)}", "error")
                    return redirect(url_for("view_results", file_id=cdr_file.id))

            except Exception as e:
                logging.error(f"Error uploading file: {str(e)}")
                flash(f"Error uploading file: {str(e)}", "error")
                return redirect(request.url)
        else:
            flash(
                "Invalid file type. Allowed types: " + ", ".join(ALLOWED_EXTENSIONS),
                "error",
            )
            return redirect(request.url)

    return render_template("upload.html")


@app.route("/results/<int:file_id>")
def view_results(file_id):
    cdr_file = CDRFile.query.get_or_404(file_id)

    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = 50

    # Get search parameters
    search_query = request.args.get("search", "")
    record_type_filter = request.args.get("record_type", "")

    # Build query with filters
    query = CDRRecord.query.filter_by(file_id=file_id)

    if search_query:
        query = query.filter(
            db.or_(
                CDRRecord.calling_number.contains(search_query),
                CDRRecord.called_number.contains(search_query),
            )
        )

    if record_type_filter:
        query = query.filter(CDRRecord.record_type == record_type_filter)

    # Get paginated results
    records = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get unique record types for filter
    record_types = (
        db.session.query(CDRRecord.record_type)
        .filter_by(file_id=file_id)
        .distinct()
        .all()
    )
    record_types = [rt[0] for rt in record_types if rt[0]]

    return render_template(
        "results.html",
        cdr_file=cdr_file,
        records=records,
        record_types=record_types,
        search_query=search_query,
        record_type_filter=record_type_filter,
    )


@app.route("/export/<int:file_id>/<format>")
def export_data(file_id, format):
    cdr_file = CDRFile.query.get_or_404(file_id)
    records = CDRRecord.query.filter_by(file_id=file_id).all()

    if format == "json":
        # Export as JSON
        data = []
        for record in records:
            data.append(record.get_raw_data())

        response = Response(
            json.dumps(data, indent=2, default=str),
            mimetype="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={cdr_file.original_filename}.json"
            },
        )
        return response

    elif format == "csv":
        # Export as CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "Record Index",
                "Record Type",
                "Calling Number",
                "Called Number",
                "Call Duration (sec)",
                "Start Time",
                "End Time",
            ]
        )

        # Write data
        for record in records:
            writer.writerow(
                [
                    record.record_index,
                    record.record_type or "",
                    record.calling_number or "",
                    record.called_number or "",
                    record.call_duration or "",
                    record.start_time or "",
                    record.end_time or "",
                ]
            )

        output.seek(0)
        response = Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={cdr_file.original_filename}.csv"
            },
        )
        return response

    else:
        flash("Invalid export format", "error")
        return redirect(url_for("view_results", file_id=file_id))


@app.route("/record/<int:record_id>")
def view_record_details(record_id):
    record = CDRRecord.query.get_or_404(record_id)
    raw_data = record.get_raw_data()

    return jsonify(
        {
            "success": True,
            "record": {
                "id": record.id,
                "record_type": record.record_type,
                "calling_number": record.calling_number,
                "called_number": record.called_number,
                "call_duration": record.call_duration,
                "start_time": str(record.start_time) if record.start_time else None,
                "end_time": str(record.end_time) if record.end_time else None,
                "raw_data": raw_data,
            },
        }
    )


@app.route("/edit/<int:record_id>")
def edit_record(record_id):
    record = CDRRecord.query.get_or_404(record_id)
    cdr_file = record.file
    return render_template("edit_record.html", record=record, cdr_file=cdr_file)


@app.route("/edit/<int:record_id>", methods=["POST"])
def update_record(record_id):
    record = CDRRecord.query.get_or_404(record_id)

    try:
        # Update basic fields
        record.record_type = request.form.get("record_type", "").strip()
        record.calling_number = request.form.get("calling_number", "").strip() or None
        record.called_number = request.form.get("called_number", "").strip() or None

        # Update duration
        duration_str = request.form.get("call_duration", "").strip()
        if duration_str:
            try:
                record.call_duration = int(duration_str)
            except ValueError:
                record.call_duration = None
        else:
            record.call_duration = None

        # Update timestamps
        start_time_str = request.form.get("start_time", "").strip()
        if start_time_str:
            try:
                record.start_time = datetime.strptime(
                    start_time_str, "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                record.start_time = None
        else:
            record.start_time = None

        end_time_str = request.form.get("end_time", "").strip()
        if end_time_str:
            try:
                record.end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                record.end_time = None
        else:
            record.end_time = None

        # Update raw data if provided
        raw_data_str = request.form.get("raw_data", "").strip()
        if raw_data_str:
            try:
                raw_data = json.loads(raw_data_str)
                record.set_raw_data(raw_data)
            except json.JSONDecodeError:
                flash("Invalid JSON format in raw data field", "error")
                return redirect(url_for("edit_record", record_id=record_id))

        db.session.commit()

        # Persist edited numbers back to the uploaded file
        cdr_file = record.file
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)
        parser = CDRParser()
        all_records = (
            CDRRecord.query.filter_by(file_id=cdr_file.id)
            .order_by(CDRRecord.record_index)
            .all()
        )
        records_data = []
        for r in all_records:
            data = r.get_raw_data()
            if "calling_number" not in data:
                data["calling_number"] = r.calling_number
            records_data.append(data)

        parser.save_records_to_file(filepath, records_data)

        flash("Record updated successfully", "success")
        return redirect(url_for("view_results", file_id=record.file_id))

    except Exception as e:
        logging.error(f"Error updating record: {str(e)}")
        flash(f"Error updating record: {str(e)}", "error")
        return redirect(url_for("edit_record", record_id=record_id))


@app.route("/create_record/<int:file_id>")
def create_record_form(file_id):
    cdr_file = CDRFile.query.get_or_404(file_id)
    return render_template("create_record.html", cdr_file=cdr_file)


@app.route("/create_record/<int:file_id>", methods=["POST"])
def create_record(file_id):
    cdr_file = CDRFile.query.get_or_404(file_id)

    try:
        # Get the next record index
        max_index = (
            db.session.query(db.func.max(CDRRecord.record_index))
            .filter_by(file_id=file_id)
            .scalar()
        )
        next_index = (max_index or -1) + 1

        # Create new record
        record = CDRRecord(
            file_id=file_id,
            record_index=next_index,
            record_type=request.form.get("record_type", "").strip() or "manual",
            calling_number=request.form.get("calling_number", "").strip() or None,
            called_number=request.form.get("called_number", "").strip() or None,
        )

        # Set duration
        duration_str = request.form.get("call_duration", "").strip()
        if duration_str:
            try:
                record.call_duration = int(duration_str)
            except ValueError:
                pass

        # Set timestamps
        start_time_str = request.form.get("start_time", "").strip()
        if start_time_str:
            try:
                record.start_time = datetime.strptime(
                    start_time_str, "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                pass

        end_time_str = request.form.get("end_time", "").strip()
        if end_time_str:
            try:
                record.end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        # Set raw data
        raw_data_str = request.form.get("raw_data", "").strip()
        if raw_data_str:
            try:
                raw_data = json.loads(raw_data_str)
                record.set_raw_data(raw_data)
            except json.JSONDecodeError:
                flash("Invalid JSON format in raw data field", "error")
                return redirect(url_for("create_record_form", file_id=file_id))

        db.session.add(record)

        # Update file record count
        cdr_file.records_count = CDRRecord.query.filter_by(file_id=file_id).count() + 1

        db.session.commit()

        # Persist new records back to the uploaded file
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)
        parser = CDRParser()
        all_records = (
            CDRRecord.query.filter_by(file_id=cdr_file.id)
            .order_by(CDRRecord.record_index)
            .all()
        )
        records_data = []
        for r in all_records:
            data = r.get_raw_data()
            if "calling_number" not in data:
                data["calling_number"] = r.calling_number
            records_data.append(data)
        parser.save_records_to_file(filepath, records_data)

        flash("Record created successfully", "success")
        return redirect(url_for("view_results", file_id=file_id))

    except Exception as e:
        logging.error(f"Error creating record: {str(e)}")
        flash(f"Error creating record: {str(e)}", "error")
        return redirect(url_for("create_record_form", file_id=file_id))


@app.route("/delete_record/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    record = CDRRecord.query.get_or_404(record_id)
    file_id = record.file_id

    try:
        db.session.delete(record)

        # Update file record count
        cdr_file = CDRFile.query.get(file_id)
        cdr_file.records_count = CDRRecord.query.filter_by(file_id=file_id).count() - 1

        db.session.commit()

        # Persist deletion to the file
        cdr_file = CDRFile.query.get(file_id)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)
        parser = CDRParser()
        all_records = (
            CDRRecord.query.filter_by(file_id=file_id)
            .order_by(CDRRecord.record_index)
            .all()
        )
        records_data = []
        for r in all_records:
            data = r.get_raw_data()
            if "calling_number" not in data:
                data["calling_number"] = r.calling_number
            records_data.append(data)
        parser.save_records_to_file(filepath, records_data)

        flash("Record deleted successfully", "success")
    except Exception as e:
        logging.error(f"Error deleting record: {str(e)}")
        flash(f"Error deleting record: {str(e)}", "error")

    return redirect(url_for("view_results", file_id=file_id))


@app.route("/delete/<int:file_id>", methods=["POST"])
def delete_file(file_id):
    cdr_file = CDRFile.query.get_or_404(file_id)

    try:
        # Delete the physical file
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)
        if os.path.exists(filepath):
            os.remove(filepath)

        # Delete from database (records will be deleted due to cascade)
        db.session.delete(cdr_file)
        db.session.commit()

        flash("File deleted successfully", "success")
    except Exception as e:
        logging.error(f"Error deleting file: {str(e)}")
        flash(f"Error deleting file: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/save_as/<int:file_id>", methods=["GET", "POST"])
def save_as(file_id):
    """Save the parsed records to a new file and database entry."""
    cdr_file = CDRFile.query.get_or_404(file_id)

    if request.method == "POST":
        new_name = request.form.get("filename", "").strip()
        if not new_name:
            flash("Filename is required", "error")
            return redirect(request.url)

        if not allowed_file(new_name):
            flash(
                "Invalid file type. Allowed types: " + ", ".join(ALLOWED_EXTENSIONS),
                "error",
            )
            return redirect(request.url)

        try:
            start_idx = int(request.form.get("start_index", 0))
        except ValueError:
            start_idx = 0
        try:
            end_idx = int(request.form.get("end_index", cdr_file.records_count - 1))
        except ValueError:
            end_idx = cdr_file.records_count - 1

        if start_idx < 0:
            start_idx = 0
        if end_idx >= cdr_file.records_count:
            end_idx = cdr_file.records_count - 1
        if end_idx < start_idx:
            flash("Invalid record range", "error")
            return redirect(request.url)

        new_filename = secure_filename(new_name)
        new_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
        if os.path.exists(new_path):
            flash("File already exists", "error")
            return redirect(request.url)

        # Copy the original file first
        original_path = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)
        shutil.copy2(original_path, new_path)

        parser = CDRParser()
        selected_records = (
            CDRRecord.query.filter_by(file_id=cdr_file.id)
            .filter(CDRRecord.record_index >= start_idx)
            .filter(CDRRecord.record_index <= end_idx)
            .order_by(CDRRecord.record_index)
            .all()
        )
        records_data = []
        for r in selected_records:
            data = r.get_raw_data()
            if "calling_number" not in data:
                data["calling_number"] = r.calling_number
            records_data.append(data)

        parser.save_records_to_file(new_path, records_data)
        file_size = os.path.getsize(new_path)

        new_file = CDRFile(
            filename=new_filename,
            original_filename=new_filename,
            file_size=file_size,
            parse_status="success",
            records_count=len(records_data),
        )
        db.session.add(new_file)
        db.session.commit()

        for i, r in enumerate(selected_records):
            new_record = CDRRecord(
                file_id=new_file.id,
                record_index=i,
                record_type=r.record_type,
                calling_number=r.calling_number,
                called_number=r.called_number,
                call_duration=r.call_duration,
                start_time=r.start_time,
                end_time=r.end_time,
            )
            new_record.set_raw_data(r.get_raw_data())
            db.session.add(new_record)

        db.session.commit()
        flash(f"File saved as {new_filename}", "success")
        return redirect(url_for("view_results", file_id=new_file.id))

    return render_template("save_as.html", cdr_file=cdr_file, ALLOWED_EXTENSIONS=ALLOWED_EXTENSIONS)


@app.route("/parse_next/<int:file_id>", methods=["POST"])
def parse_next(file_id):
    """Parse the next 100 records from the CDR file."""
    cdr_file = CDRFile.query.get_or_404(file_id)
    start_index = CDRRecord.query.filter_by(file_id=file_id).count()
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], cdr_file.filename)

    parser = CDRParser()
    records, reached_end, new_offset = parser.parse_file_chunk(
        filepath,
        start_record=start_index,
        max_records=100,
        offset=cdr_file.parse_offset,
    )

    if not records:
        flash("No more records found", "info")
        return redirect(url_for("view_results", file_id=file_id))

    for i, record in enumerate(records):
        cdr_record = CDRRecord(
            file_id=file_id,
            record_index=start_index + i,
            record_type=record.get("record_type", "unknown"),
            calling_number=record.get("calling_number"),
            called_number=record.get("called_number"),
            call_duration=record.get("call_duration"),
            start_time=record.get("start_time"),
            end_time=record.get("end_time"),
        )
        cdr_record.set_raw_data(record)
        db.session.add(cdr_record)

    cdr_file.records_count = start_index + len(records)
    cdr_file.parse_offset = new_offset
    db.session.commit()
    if reached_end:
        flash(
            f"Parsed {len(records)} records and reached end of file",
            "success",
        )
    else:
        flash(f"Parsed {len(records)} additional records", "success")
    return redirect(url_for("view_results", file_id=file_id))
