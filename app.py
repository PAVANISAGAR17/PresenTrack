from flask import Flask, render_template, request, send_file
import pandas as pd
import os
import chardet
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def detect_encoding(filepath):
    """Detect the encoding of a file."""
    with open(filepath, "rb") as f:
        result = chardet.detect(f.read(100000))  # Read first 100,000 bytes
        return result["encoding"]

def process_csv(filepath, threshold_seconds):
    """Process the uploaded CSV file and determine presentees/absentees."""
    encoding_used = detect_encoding(filepath)
    df = pd.read_csv(filepath, encoding=encoding_used, delimiter="\t")
    
    # Check if required columns exist
    required_columns = {"Full Name", "User Action", "Timestamp"}
    if not required_columns.issubset(df.columns):
        raise KeyError("CSV file does not have the required columns: Full Name, User Action, Timestamp")
    
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df.sort_values(by=["Full Name", "Timestamp"], inplace=True)
    
    # Compute duration for each participant
    df["Duration"] = df.groupby("Full Name")["Timestamp"].diff().dt.total_seconds()
    df.fillna(0, inplace=True)
    
    # Handling users who never left
    last_timestamp = df["Timestamp"].max()  # Last recorded time in the session
    user_first_entry = df.groupby("Full Name")["Timestamp"].first()  # First login time per user
    
    # Compute total duration (including users who never left)
    total_duration_per_user = df.groupby("Full Name")["Duration"].sum()
    
    for user, first_time in user_first_entry.items():
        if total_duration_per_user[user] == 0:  # User has only one entry (joined but never left)
            total_duration_per_user[user] = (last_timestamp - first_time).total_seconds()
    
    # Create attendance report
    attendance_df = pd.DataFrame({"Full Name": total_duration_per_user.index, "Total Duration (secs)": total_duration_per_user.values})
    attendance_df["Status"] = attendance_df["Total Duration (secs)"].apply(lambda x: "Present" if x >= threshold_seconds else "Absent")
    
    output_filepath = os.path.join(PROCESSED_FOLDER, "attendance_output.csv")
    attendance_df.to_csv(output_filepath, index=False, encoding=encoding_used, sep="\t")
    
    return output_filepath

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        threshold_seconds = request.form.get("threshold", type=int, default=0)
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            try:
                output_filepath = process_csv(filepath, threshold_seconds)
                return send_file(output_filepath, as_attachment=True)
            except KeyError as e:
                return f"Error: {str(e)}"
            
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
