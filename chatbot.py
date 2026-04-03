import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

app = Flask(__name__)

CORS(app)

# =========================
# 🔐 Gemini API Setup
# =========================
try:
    from openai import OpenAI

    # api_key = os.getenv("GEMINI_API_KEY")
    api_key = "AIzaSyCxVXf5a4kthiSWkZDi8pzgffShGaAUrnk"
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    gemini_available = True

except Exception as e:
    print("Gemini Error:", e)
    gemini_available = False


# =========================
# 🗄️ MongoDB Setup
# =========================
try:
    import pymongo

    mongo_client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    mongo_client.server_info()  # Force connection check

    db = mongo_client["chatbot_db"]
    users_collection = db["users"]
    chat_collection = db["chat_history"]

    mongo_available = True

except Exception as e:
    print("MongoDB Error:", e)
    mongo_available = False


# =========================
# 🔑 Simple Token Storage
# =========================
active_sessions = {}  # token -> user_id


# =========================
# 🤖 Gemini Function
# =========================
def ask_gemini(prompt, history=None):
    if not gemini_available:
        return "Gemini not available"

    try:
        messages = [{"role": "system", "content": "You are a helpful assistant."}]

        if history:
            for h in history:
                messages.append({"role": "user", "content": h["user"]})
                messages.append({"role": "assistant", "content": h["agent"]})

        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=messages,
            temperature=0.7
        )

        # return response.choices[0].message["content"]
        return  response.choices[0].message.content

    except Exception as e:
        return f"Gemini Error: {str(e)}"


# =========================
# 🧑 Signup
# =========================
@app.route("/signup", methods=["POST"])
def signup():
    if not mongo_available:
        return jsonify({"error": "DB not available"}), 500

    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400

    if users_collection.find_one({"username": username}):
        return jsonify({"error": "User exists"}), 409

    hashed_pw = generate_password_hash(password)

    user_id = str(uuid.uuid4())

    users_collection.insert_one({
        "user_id": user_id,
        "username": username,
        "password": hashed_pw
    })

    return jsonify({"message": "Signup successful"}), 201


# =========================
# 🔐 Login
# =========================
@app.route("/login", methods=["POST"])
def login():
    if not mongo_available:
        return jsonify({"error": "DB not available"}), 500

    data = request.json
    username = data.get("username")
    password = data.get("password")

    user = users_collection.find_one({"username": username})

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Create token
    token = str(uuid.uuid4())
    active_sessions[token] = user["user_id"]

    return jsonify({
        "message": "Login successful",
        "token": token
    })


# =========================
# 💬 Chat
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    if not mongo_available:
        return jsonify({"error": "DB not available"}), 500

    token = request.headers.get("Authorization")

    if not token or token not in active_sessions:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = active_sessions[token]

    data = request.json
    prompt = data.get("prompt")

    if not prompt:
        return jsonify({"error": "Prompt required"}), 400

    # Fetch history
    history = list(chat_collection.find({"user_id": user_id}).sort("time", -1).limit(5))
    history.reverse()

    reply = ask_gemini(prompt, history)

    chat_collection.insert_one({
        "user_id": user_id,
        "user": prompt,
        "agent": reply,
        "time": datetime.now()
    })

    return jsonify({"reply": reply})


# =========================
# 🚀 Run App
# =========================
if __name__ == "__main__":
    print("Server running on http://127.0.0.1:5000")
    app.run(debug=True)