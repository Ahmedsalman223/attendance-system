import time
import math
import pyotp
import qrcode
import io
import os
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# مفتاح سري محلي لتوليد الـ QR الديناميكي (Dynamic Tokenization)
SECRET_KEY = pyotp.random_base32()
totp = pyotp.TOTP(SECRET_KEY, interval=10) # يتغير كل 10 ثوانٍ

# إحداثيات قاعة المحاضرات (افتراضية للمثال)
HALL_LAT = 31.0409
HALL_LON = 31.3785
ALLOWED_RADIUS_METERS = 50.0  # المدى المسموح به بالمتور

def haversine(lat1, lon1, lat2, lon2):
    """حساب المسافة بين نقطتين جغرافيين بالمتر"""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# قاعدة بيانات مؤقتة في الذاكرة لمنع تسجيل الجهاز أكثر من مرة
registered_devices = {}
attendance_records = []

@app.route('/')
def home():
    return render_template('student.html')

@app.route('/doctor')
def doctor():
    return render_template('doctor.html')

@app.route('/student')
def student():
    return render_template('student.html')

@app.route('/api/get-qr-token')
def get_qr_token():
    """توليد كود الـ QR الديناميكي لشاشة الدكتور"""
    current_token = totp.now()
    img = qrcode.make(current_token)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/get-token-text')
def get_token_text():
    """إرجاع النص الحالي للرمز للاستخدام اليدوي للطوارئ"""
    return jsonify({"token": totp.now()})

@app.route('/api/submit-attendance', methods=['POST'])
def submit_attendance():
    """التحقق من صحة عملية التسجيل (الـ QR + الـ GPS + بصمة الجهاز)"""
    data = request.json or {}
    student_id = data.get('student_id')
    user_token = data.get('token')
    user_lat = data.get('lat')
    user_lon = data.get('lon')
    device_fingerprint = data.get('device_fingerprint')

    if not all([student_id, user_token, user_lat, user_lon, device_fingerprint]):
        return jsonify({"status": "error", "message": "بيانات غير مكتملة!"}), 400

    # 1. التحقق من صحة رمز الـ QR (Dynamic Token Verification)
    if not totp.verify(user_token, valid_window=1):
        return jsonify({"status": "error", "message": "رمز الـ QR منتهي الصلاحية أو غير صحيح!"}), 400

    # 2. التحقق من الموقع الجغرافي (Geofencing)
    distance = haversine(float(user_lat), float(user_lon), HALL_LAT, HALL_LON)
    if distance > ALLOWED_RADIUS_METERS:
        return jsonify({
            "status": "error", 
            "message": f"عفواً! أنت خارج نطاق القاعة. المسافة الحالية: {int(distance)} متر."
        }), 403

    # 3. التحقق من تقييد الجهاز (Device Binding)
    if student_id in registered_devices:
        if registered_devices[student_id] != device_fingerprint:
            return jsonify({
                "status": "error", 
                "message": "عفواً! لا يمكنك التسجيل من جهاز مختلف عن الجهاز المربوط بحسابك."
            }), 403
    else:
        registered_devices[student_id] = device_fingerprint

    # تسجيل الحضور بنجاح
    attendance_records.append({
        "student_id": student_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": device_fingerprint
    })

    return jsonify({
        "status": "success", 
        "message": f"تم تسجيل حضور الطالب {student_id} بنجاح! 🎯"
    }), 200

if __name__ == '__main__':
    # القراءة التلقائية للبورت المناسب للـ Cloud Hosting
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)