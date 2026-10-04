from flask import Flask, render_template, request, redirect, session, send_file
from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
from reportlab.pdfgen import canvas
import os
import requests
import random
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secretkey123"

from flask_mail import Mail, Message

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_app_password'
app.config['MAIL_USE_TLS'] = True

mail = Mail(app)


# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="ai_learning_platform"
    )


def send_security_alert(user_name):
    msg = Message(
        subject="🚨 SECURITY ALERT",
        sender=app.config['MAIL_USERNAME'],
        recipients=['admin@gmail.com']
    )

    msg.body = f"""
    ALERT!

    User '{user_name}' tried to change ADMIN password.

    Check your system immediately.
    """

    mail.send(msg)



@app.route("/change_admin_password", methods=["POST"])
def change_admin_password():

    user_name = session.get("user_name", "Unknown")
    role = session.get("role")

    conn = get_db_connection()
    cursor = conn.cursor()

    # ❌ If NOT admin → BLOCK + ALERT
    if role != "admin":

        # Save notification in DB
        cursor.execute(
            "INSERT INTO notifications (message) VALUES (%s)",
            (f"{user_name} tried to change admin password",)
        )
        conn.commit()

        conn.close()

        # Send email
        send_security_alert(user_name)

        return "🚨 Unauthorized attempt detected!"

    # ✅ If admin → allow password change
    new_password = request.form.get("new_password")

    cursor.execute(
        "UPDATE users SET u_password=%s WHERE u_role='admin'",
        (new_password,)
    )

    conn.commit()
    conn.close()

    return "✅ Admin password updated successfully"


@app.route("/get_notifications")
def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 5")
    data = cursor.fetchall()

    conn.close()

    return jsonify(data)
# ---------------- HOME PAGE ----------------
@app.route('/')
def home():
    return render_template("home.html")


@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Connect to database
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            from werkzeug.security import check_password_hash
            cursor.execute("SELECT * FROM users WHERE u_email=%s", (email,))
            user = cursor.fetchone()

        except Exception as e:
            print("DB Error:", e)
            return "Database connection failed!"

        finally:
            # Close connection safely if it exists
            if 'conn' in locals() and conn.is_connected():
                conn.close()

        # Check if user exists
        if not user:
            return "Invalid email or password!"

        # Clear previous session and set new session
        session.clear()
        session['user_id'] = user['u_id']
        session['role'] = user['u_role']
        session['user_name'] = user['u_name']  

        # Redirect based on role
        if user['u_role'] == "student":
            return redirect('/student_dashboard')
        else:
            return redirect('/admin_dashboard')

    # GET request
    if session.get('role') and session.get('user_id'):
        if session['role'] == 'student':
            return redirect('/student_dashboard')
        else:
            return redirect('/admin_dashboard')

    return render_template("login.html")

@app.route("/users")
def users():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    #  Only fetch students (NOT admin)
    cursor.execute("SELECT u_name, u_email FROM users WHERE u_role = 'student'")
    users = cursor.fetchall()

    total_users = len(users)

    conn.close()

    return render_template("users.html",
                           users=users,
                           total_users=total_users)
# ---------------- admin dashboard ----------------
@app.route("/admin_dashboard")
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    #  Total Users
    cursor.execute("SELECT COUNT(*) as total FROM users")
    users = cursor.fetchone()['total']

    # 📚Total Courses (quiz_topics table)
    cursor.execute("SELECT COUNT(*) as total FROM quiz_topics")
    courses = cursor.fetchone()['total']

    #  Total Quizzes
    cursor.execute("SELECT COUNT(*) as total FROM quiz_questions")
    quizzes = cursor.fetchone()['total']

    # Average Score
    cursor.execute("SELECT AVG(score) as avg_score FROM results")
    avg_score = cursor.fetchone()['avg_score']
    avg_score = round(avg_score, 2) if avg_score else 0

    conn.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        courses=courses,   # ✅ IMPORTANT
        quizzes=quizzes,
        avg_score=avg_score
    )
# ---------------- SIGNUP ----------------
from werkzeug.security import generate_password_hash

@app.route('/signup', methods=['GET','POST'])
def signup():

    if request.method == 'POST':

        name = request.form['username']
        email = request.form['email']
        password = request.form['password']
        mobile = request.form.get('mobile')
        if not mobile:
            return "Mobile number is required!"

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check email already exists
        cursor.execute("SELECT * FROM users WHERE u_email=%s",(email,))
        user_email = cursor.fetchone()

        #  Check mobile already exists
        cursor.execute("SELECT * FROM users WHERE u_mobile=%s",(mobile,))
        user_mobile = cursor.fetchone()

        if user_email:
            conn.close()
            return "Email already registered!"

        if user_mobile:
            conn.close()
            return "Mobile number already registered!"

        #  Hash password
        hashed_password = generate_password_hash(password)

        #  Insert user
        cursor.execute("""
        INSERT INTO users (u_name, u_email, u_password, u_role, u_flag, u_mobile)
        VALUES (%s,%s,%s,'student',1,%s)
        """,(name,email,hashed_password,mobile))

        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template("signup.html")

@app.route("/search_users")
def search_users():
    query = request.args.get("q")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, course, status 
        FROM users 
        WHERE name LIKE ? OR course LIKE ? OR status LIKE ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%"))

    results = cursor.fetchall()
    conn.close()

    data = []
    for row in results:
        data.append({
            "name": row[0],
            "course": row[1],
            "status": row[2]
        })

    return jsonify(data)

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student_dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect('/login')
    
    student_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch topics
    cursor.execute("SELECT topic_id, topic_name FROM quiz_topics")
    topics = cursor.fetchall()

    # Fetch student results
    cursor.execute("""
        SELECT qt.topic_name, r.score, r.total_questions, r.taken_at
        FROM results r
        JOIN quiz_topics qt ON r.topic_id = qt.topic_id
        WHERE r.u_id = %s
        ORDER BY r.taken_at ASC
    """, (student_id,))
    results = cursor.fetchall()
    conn.close()

    # Calculate overall progress
    overall_progress = 0
    if results:
        total_score = sum(r['score'] for r in results)
        total_questions = sum(r['total_questions'] for r in results)
        overall_progress = int((total_score / total_questions) * 100) if total_questions > 0 else 0

    # Prepare chart data
    chart_data = {}
    for r in results:
        subject = r['topic_name']
        if subject not in chart_data:
            chart_data[subject] = {"dates": [], "scores": []}
        chart_data[subject]["dates"].append(r['taken_at'].strftime("%Y-%m-%d"))
        chart_data[subject]["scores"].append(int((r['score']/r['total_questions'])*100))

    user_name = session.get("user_name", "Student")

    return render_template(
        "student_dashboard.html",
        topics=topics,
        user_name=user_name,
        progress=overall_progress,
        chart_data=chart_data
    )

# ---------------- VIEW COURSES ----------------
@app.route('/view_courses')
def view_courses():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM quiz_topics")
    topics = cursor.fetchall()
    conn.close()

    return render_template("view_courses.html", topics=topics)


@app.route('/courses', methods=['GET', 'POST'])
def courses():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    #  SEARCH
    search = request.args.get('search')

    if search:
        cursor.execute("SELECT * FROM quiz_topics WHERE topic_name LIKE %s", (f"%{search}%",))
    else:
        cursor.execute("SELECT * FROM quiz_topics")

    courses = cursor.fetchall()

    conn.close()

    return render_template("cources.html", courses=courses)

@app.route('/delete_topic/<int:id>')
def delete_topic(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM quiz_topics WHERE topic_id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect('/cources')

from flask import request, jsonify

@app.route('/update_topic/<int:id>', methods=['POST'])
def update_topic(id):
    data = request.get_json()
    new_name = data.get('topic_name')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE quiz_topics SET topic_name=%s WHERE topic_id=%s", (new_name, id))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})

# ---------------- LEVEL PAGE ----------------
@app.route('/levels/<int:topic_id>')
def levels(topic_id):

    if session.get('role') != 'student':
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT level, score, total_questions, taken_at
        FROM results
        WHERE u_id=%s AND topic_id=%s
        ORDER BY level
    """, (user_id, topic_id))

    results = cursor.fetchall()

    completed_levels = [r['level'] for r in results if r['level'] is not None]

    if completed_levels:
        next_level = max(completed_levels) + 1
    else:
        next_level = 1

    conn.close()

    return render_template(
        "levels.html",
        topic_id=topic_id,
        results=results,
        completed_levels=completed_levels,
        next_level=next_level
    )

# ---------------- START QUIZ ----------------
@app.route('/start_quiz/<int:topic_id>/<int:level>', methods=['GET', 'POST'])
def start_quiz(topic_id, level):

    if session.get('role') != 'student':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    if session.get('topic_id') != topic_id or session.get('level') != level:
        session.pop('question_ids', None)
        session.pop('current_index', None)
        session.pop('score', None)
        session['topic_id'] = topic_id
        session['level'] = level

    if topic_id == 12:

        if level > 1:
            cursor.execute("""
                SELECT 1 FROM results
                WHERE u_id=%s AND topic_id=%s AND level=%s
                LIMIT 1
            """, (user_id, topic_id, level - 1))

            prev_level = cursor.fetchone()

            if not prev_level:
                conn.close()
                return "You must complete previous C++ level first!"

    else:
        if level > 1:
            cursor.execute("""
                SELECT 1 FROM results
                WHERE u_id=%s AND topic_id=%s AND level=%s
                LIMIT 1
            """, (user_id, topic_id, level - 1))

            prev_level = cursor.fetchone()

            if not prev_level:
                conn.close()
                return "Complete previous level first!"

    # ---------- LOAD QUESTIONS ----------
    if 'question_ids' not in session:

        cursor.execute("""
            SELECT q_id FROM quiz_questions
            WHERE topic_id=%s AND level=%s
        """, (topic_id, level))

        all_questions = cursor.fetchall()

        if not all_questions:
            conn.close()
            return "No questions available."

        question_ids = [q['q_id'] for q in all_questions]
        random.shuffle(question_ids)

        session['question_ids'] = question_ids[:10]
        session['current_index'] = 0
        session['score'] = 0

    index = session['current_index']
    question_ids = session['question_ids']

    # ---------- QUIZ FINISHED ----------
    if index >= len(question_ids):

        final_score = session['score']
        total_questions = len(question_ids)
        percentage = (final_score / total_questions) * 100
        passed = percentage >= 50

        cursor.execute("""
            INSERT INTO results (u_id, topic_id, level, score, total_questions)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, topic_id, level, final_score, total_questions))

        conn.commit()

        cursor.execute("""
            SELECT u.u_email, r.score
            FROM results r
            JOIN users u ON r.u_id = u.u_id
            WHERE r.topic_id=%s AND r.level=%s
            ORDER BY r.score DESC
            LIMIT 5
        """, (topic_id, level))

        leaderboard = cursor.fetchall()

        session.pop('question_ids', None)
        session.pop('current_index', None)
        session.pop('score', None)

        conn.close()

        return render_template(
            "quiz_result.html",
            score=final_score,
            total=total_questions,
            percentage=percentage,
            passed=passed,
            topic_id=topic_id,
            level=level,
            leaderboard=leaderboard
        )

    # ---------- CURRENT QUESTION ----------
    current_q_id = question_ids[index]

    cursor.execute("""
        SELECT * FROM quiz_questions
        WHERE q_id=%s
    """, (current_q_id,))

    question = cursor.fetchone()

    feedback = None
    selected_option = None

    # ---------- ANSWER HANDLING ----------
    if request.method == "POST":

        if 'prev' in request.form:
            if session.get('current_index', 0) > 0:
                session['current_index'] -= 1
            conn.close()
            return redirect(f"/start_quiz/{topic_id}/{level}")

        elif "next" in request.form:
            session['current_index'] += 1
            conn.close()
            return redirect(f"/start_quiz/{topic_id}/{level}")

        selected_option = request.form.get("answer")

        if selected_option == question["correct_option"]:
            session['score'] += 1
            session['current_index'] += 1
            conn.close()
            return redirect(f"/start_quiz/{topic_id}/{level}")
        else:
            feedback = {
                "correct_answer": question["correct_option"],
                "explanation": question["explanation"]
            }

    conn.close()

    return render_template(
        "start_quiz.html",
        question=question,
        question_number=index + 1,
        score=session.get('score', 0),
        feedback=feedback,
        level=level,
        selected_option=selected_option,
        total=len(question_ids)
    )
# ---------------- CHATBOT MAIN TOPICS ----------------
@app.route('/chatbot')
def chatbot_topics():

    if session.get('role') != 'student':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM quiz_topics")
    topics = cursor.fetchall()
    conn.close()

    return render_template("chatbot_topics.html", topics=topics)



from werkzeug.security import generate_password_hash

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    message = ""
    category = ""

    if request.method == 'POST':
        number = request.form.get('number')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        #  Validate inputs
        if not number or not new_password or not confirm_password:
            return render_template("forgot_password.html",
                                   message="All fields are required!",
                                   category="error")

        # Password match check
        if new_password != confirm_password:
            return render_template("forgot_password.html",
                                   message="Passwords do not match!",
                                   category="error")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        #  STEP 1: Check if mobile exists
        cursor.execute("SELECT * FROM users WHERE u_mobile=%s", (number,))
        user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return render_template("forgot_password.html",
                                   message="❌ Enter only registered mobile number!",
                                   category="error")

        # STEP 2: Hash password
        hashed_password = generate_password_hash(new_password)

        # STEP 3: Update password
        cursor.execute("""
            UPDATE users
            SET u_password=%s
            WHERE u_mobile=%s
        """, (hashed_password, number))

        conn.commit()
        cursor.close()
        conn.close()

        return render_template("forgot_password.html",
                               message=" Password updated successfully!",
                               category="success")

    return render_template("forgot_password.html")

# ---------------- CHATBOT SUBTOPICS ----------------
@app.route('/chatbot/<int:topic_id>')
def chatbot_subtopics(topic_id):

    if session.get('role') != 'student':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT topic_name FROM quiz_topics WHERE topic_id=%s", (topic_id,))
    topic = cursor.fetchone()
    conn.close()

    if not topic:
        return "Topic not found"

    topic_name = topic['topic_name']

    # Simple syllabus style subtopics
    subtopics = [
        f"Introduction to {topic_name}",
        f"Functions in {topic_name}",
        f"Advantages of {topic_name}",
        f"Examples of {topic_name}",
        f"Applications of {topic_name}"
    ]

    return render_template("chatbot_subtopics.html",
                           topic_id=topic_id,
                           topic_name=topic_name,
                           subtopics=subtopics)


# ---------------- REAL CHATBOT ----------------
@app.route('/chatbot/<int:topic_id>/chat', methods=['GET', 'POST'])
def chatbot_chat(topic_id):

    if session.get('role') != 'student':
        return redirect('/login')

    # ---------------- GET TOPIC ----------------
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT topic_name FROM quiz_topics WHERE topic_id=%s", (topic_id,))
    topic = cursor.fetchone()
    conn.close()

    if not topic:
        return "Topic not found"

    topic_name = topic['topic_name']

    # ---------------- RESET CHAT WHEN TOPIC CHANGES ----------------
    if session.get('current_topic') != topic_id:
        session['chat_history'] = []
        session['current_topic'] = topic_id

    if 'chat_history' not in session:
        session['chat_history'] = []

    # ---------------- HANDLE USER MESSAGE ----------------
    if request.method == "POST":

        user_message = request.form.get("message")

        if user_message:

            # Save user message
            session['chat_history'].append({
                "role": "user",
                "content": user_message
            })

            greetings = ["hi", "hello", "hey", "hii"]

            if user_message.lower().strip() in greetings:
                ai_reply = f"Hello 👋 I am your {topic_name} AI Tutor. Ask me questions related to {topic_name}."

            else:
                # ---------------- STEP 1: DETECT QUESTION TYPE ----------------
                msg = user_message.lower()

                if "example" in msg:
                    prompt_type = "example"
                elif "explain" in msg:
                    prompt_type = "explain"
                elif "what is" in msg or "define" in msg:
                    prompt_type = "definition"
                else:
                    prompt_type = "general"

                # ---------------- STEP 2: STRONG PROMPT ----------------
                prompt = f"""
You are a tutor for {topic_name}.

Answer the QUESTION directly.

DO NOT give instructions.
DO NOT give tips.
DO NOT explain how to answer.
ONLY give final answer.

If question is not related to {topic_name}, reply:
❌ Not related to {topic_name}

FORMAT:

If question is "what is" or "define":
Definition:
<2 lines>

Explanation:
<3 lines>

Example:
<1 simple example>

If question asks example:
Give only 1 example.

If question asks explain:
Give only explanation.

QUESTION: {user_message}

FINAL ANSWER:
"""

                try:
                    response = requests.post(
                        "http://localhost:11434/api/generate",
                        json={
                            "model": "tinyllama",
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "num_predict": 250,   # prevent cut answers
                                "temperature": 0.1    # more accurate
                            }
                        },
                        timeout=60
                    )

                    if response.status_code == 200:
                        result = response.json()
                        ai_reply = result.get("response", "").strip()

                        # ---------------- CLEAN RESPONSE ----------------
                        if "Answer:" in ai_reply:
                            ai_reply = ai_reply.split("Answer:")[-1].strip()

                        # Format for UI
                        ai_reply = ai_reply.replace("Definition:", "<b>Definition:</b>")
                        ai_reply = ai_reply.replace("Explanation:", "<b>Explanation:</b>")
                        ai_reply = ai_reply.replace("Example:", "<b>Example:</b>")
                        ai_reply = ai_reply.replace("\n", "<br>")

                    else:
                        ai_reply = "⚠️ AI model error. Please try again."

                except Exception:
                    ai_reply = "❌ AI server not responding. Make sure model is running."

            # Save AI reply
            session['chat_history'].append({
                "role": "assistant",
                "content": ai_reply
            })

            session.modified = True

    # ---------------- RENDER ----------------
    return render_template(
        "chatbot_chat.html",
        topic_name=topic_name,
        chat_history=session.get('chat_history', []),
        topic_id=topic_id
    )
# ---------------- progress bar ----------------
@app.route("/progress")
def progress():
    if 'user_id' not in session:
        return redirect('/login')

    student_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch total score and total questions per topic
    cursor.execute("""
        SELECT qt.topic_name, 
               SUM(r.score) AS total_score, 
               SUM(r.total_questions) AS total_questions
        FROM results r
        JOIN quiz_topics qt ON r.topic_id = qt.topic_id
        WHERE r.u_id = %s
        GROUP BY r.topic_id
    """, (student_id,))

    data = cursor.fetchall()
    conn.close()

    subjects = []
    for row in data:
        percentage = int((row['total_score'] / row['total_questions']) * 100)
        subjects.append({
            "name": row['topic_name'],
            "score": percentage
        })

    overall_progress = sum(s['score'] for s in subjects) // len(subjects) if subjects else 0
    weak_subject = min(subjects, key=lambda x: x['score'])['name'] if subjects else "N/A"

    return render_template(
        "progress.html",
        subjects=subjects,
        overall_progress=overall_progress,
        weak_subject=weak_subject
    )

    # ---------------- BAR CHART ----------------
@app.route("/bar_chart")
def charts():

    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    student_id = session['user_id']

    query = """
    SELECT t.topic_name,
           SUM(r.score) as total_score,
           SUM(r.total_questions) as total_questions
    FROM results r
    JOIN quiz_topics t ON r.topic_id = t.topic_id
    WHERE r.u_id = %s
    GROUP BY r.topic_id
    """

    cursor.execute(query, (student_id,))
    data = cursor.fetchall()

    subjects = []

    for row in data:
        percentage = int((row['total_score'] / row['total_questions']) * 100)

        subjects.append({
            "name": row['topic_name'],
            "score": percentage
        })

    conn.close()

    return render_template("bar_chart.html", subjects=subjects)

   # ---------------- certificate ----------------
@app.route("/certificates/<int:topic_id>")
def certificate(topic_id):
    if 'user_id' not in session:
        return redirect('/login')

    student_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch user and topic details
    cursor.execute("SELECT u_name FROM users WHERE u_id=%s", (student_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT topic_name FROM quiz_topics WHERE topic_id=%s", (topic_id,))
    topic = cursor.fetchone()

    if not user or not topic:
        cursor.close()
        conn.close()
        return "Invalid user or topic", 404

    # Create PDF certificate
    filename = f"certificate_{student_id}_{topic_id}.pdf"
    dir_path = os.path.join("static", "certificates")
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, filename)
    if not os.path.exists(path):
        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4

    # Outer border
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(6)
        c.rect(30, 30, width-60, height-60)

    # Inner border
        c.setStrokeColor(colors.lightblue)
        c.setLineWidth(2)
        c.rect(50, 50, width-100, height-100)

    # Title
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(width/2, height-200, "CERTIFICATE")

        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width/2, height-240, "OF COMPLETION")

    # Subtitle
        c.setFont("Helvetica", 16)
        c.drawCentredString(width/2, height-300, "This certificate is awarded to")

    # Student name
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(colors.darkblue)
        c.drawCentredString(width/2, height-340, user['u_name'])

    # Topic name
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 16)
        c.drawCentredString(width/2, height-380, "For successfully completing")

        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width/2, height-410, topic['topic_name'])

    # Date
        today = datetime.today().strftime("%d %B %Y")
        c.setFont("Helvetica", 14)
        c.drawCentredString(width/2, height-460, f"Date: {today}")

    # Signature line
        c.line(width/2+120, 120, width/2+280, 120)
        c.setFont("Helvetica", 12)
        c.drawCentredString(width/2+200, 100, "Instructor Signature")

        c.save()

    # Insert into certificates table (if not already inserted)
    cursor.execute("""
        SELECT * FROM certificates
        WHERE cert_student_id=%s AND cert_topic_id=%s
    """, (student_id, topic_id))
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("""
            INSERT INTO certificates(cert_student_id, cert_topic_id, cert_filename)
            VALUES (%s, %s, %s)
        """, (student_id, topic_id, filename))
        conn.commit()

    cursor.close()
    conn.close()
    # Send file to user (disable browser caching)
    return send_file(path, as_attachment=True, max_age=0)


# ---------------- serve certificate files ----------------
@app.route("/certificates/files/<filename>")
def serve_certificate(filename):
    path = os.path.join("static", "certificates", filename)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True, max_age=0)

# ---------------- achievements ----------------
@app.route("/achievements")
def achievements():
    if 'user_id' not in session:
        return redirect('/login')

    student_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all certificates earned by the user
    cursor.execute("""
        SELECT c.cert_filename, c.cert_issued_date, qt.topic_name
        FROM certificates c
        JOIN quiz_topics qt ON c.cert_topic_id = qt.topic_id
        WHERE c.cert_student_id = %s
        ORDER BY c.cert_issued_date DESC
    """, (student_id,))

    certs = cursor.fetchall()
    total_certs = len(certs)

    cursor.close()
    conn.close()

    return render_template("achievements.html", certs=certs, total_certs=total_certs)

    # ---------------- feedback ----------------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        # Handle form submission
        # appointment_id = request.form.get("appointment_id")
        # patient_id = request.form.get("patient_id")
        # doctor_id = request.form.get("doctor_id")
        rating = request.form.get("rating")
        comment = request.form.get("comment")

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO feedback1 (rating, comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (rating, comment))
            conn.commit()
            cur.close()
            conn.close()
            return "Feedback submitted successfully!"
        except Exception as e:
            print("Database Error:", e)
            return "There was an error submitting your feedback."
    else:
        # Handle GET request – show the form
        return render_template("feedback.html")

# ---------------- VIEW RESULTS ----------------
@app.route('/view_results')
def view_results():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all results for this student
    cursor.execute("""
        SELECT r.level, r.score, r.total_questions, r.taken_at, t.topic_name
        FROM results r
        JOIN quiz_topics t ON r.topic_id = t.topic_id
        WHERE r.u_id = %s
        ORDER BY r.taken_at DESC
    """, (student_id,))

    results = cursor.fetchall()
    conn.close()

    # Calculate percentage and pass/fail
    for r in results:
        r['percentage'] = round((r['score'] / r['total_questions']) * 100, 2)
        r['status'] = "Passed ✅" if r['percentage'] >= 50 else "Failed ❌"

    return render_template("view_results.html", results=results)

@app.route("/analytics")
def analytics():
    # if session.get('role') != 'admin':
    #     return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # -------- CHART DATA --------
    cursor.execute("""
    SELECT t.topic_name,
           SUM(r.score) as total_score,
           SUM(r.total_questions) as total_questions
    FROM results r
    JOIN quiz_topics t ON r.topic_id = t.topic_id
    GROUP BY r.topic_id
    """)

    data = cursor.fetchall()

    topics = []
    scores = []

    for row in data:
        percentage = int((row['total_score'] / row['total_questions']) * 100)
        topics.append(row['topic_name'])
        scores.append(percentage)

    # -------- STUDENT ANALYTICS TABLE --------
    cursor.execute("""
    SELECT u.u_name, t.topic_name,
           MAX(r.score) as highest_score,
           MAX(r.total_questions) as total_questions
    FROM results r
    JOIN users u ON r.u_id = u.u_id
    JOIN quiz_topics t ON r.topic_id = t.topic_id
    GROUP BY u.u_id, t.topic_id
    """)

    records = cursor.fetchall()

    student_data = {}

    for row in records:
        name = row['u_name']
        topic = row['topic_name']
        score = row['highest_score']
        total = row['total_questions']

        percentage = int((score / total) * 100)

        if name not in student_data:
            student_data[name] = []

        student_data[name].append({
            "topic": topic,
            "percentage": percentage
        })

    final_table = []

    for student, subjects in student_data.items():
        # highest subject
        best = max(subjects, key=lambda x: x['percentage'])

        # weak subject
        weak = min(subjects, key=lambda x: x['percentage'])

        final_table.append({
            "student": student,
            "best_subject": best['topic'],
            "best_score": best['percentage'],
            "weak_subject": weak['topic'],
            "weak_score": weak['percentage']
        })

    conn.close()

    return render_template("analytics.html",
                           topics=topics,
                           scores=scores,
                           table=final_table)

@app.route('/add_topic', methods=['GET', 'POST'])
def add_topic():
    if session.get('role') != 'admin':
        return redirect('/login')

    if request.method == 'POST':
        topic_name = request.form.get('topic_name')

        if not topic_name:
            return "Topic name is required!"

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check duplicate
        cursor.execute("SELECT * FROM quiz_topics WHERE topic_name=%s", (topic_name,))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return "Topic already exists!"

        # Insert topic
        cursor.execute(
            "INSERT INTO quiz_topics (topic_name) VALUES (%s)",
            (topic_name,)
        )

        conn.commit()
        conn.close()

        return redirect('/admin_dashboard')

    return render_template('add_topic.html')

@app.route("/student_progress")
def student_progress():
    student_id = session.get("user_id")
    if not student_id:
        return redirect("/login")

    db, cursor = get_db_connection()

    # Fetch scores grouped by subject and date
    cursor.execute("""
        SELECT subject, date_taken, score 
        FROM student_results
        WHERE student_id=%s
        ORDER BY date_taken ASC
    """, (student_id,))
    results = cursor.fetchall()
    db.close()

    # Make sure progress & user_name exist
    user_name = session.get("user_name", "Student")
    progress = 0  # default, you can calculate average if needed

    # Organize data for chart.js
    subjects = list(set(r['subject'] for r in results))  # unique subjects
    chart_data = {}
    for subject in subjects:
        chart_data[subject] = {
            "dates": [r['date_taken'].strftime("%Y-%m-%d") for r in results if r['subject']==subject],
            "scores": [r['score'] for r in results if r['subject']==subject]
        }

    # Now return template **after all subjects are processed**
    return render_template(
        "progress.html",
        user_name=user_name,
        progress=progress,
        chart_data=chart_data
    )
            # ---------------- LOGOUT ---------------

@app.route('/logout')
def logout():
    session.clear()  # clears all session data
    return redirect(url_for('home')) 

if __name__ == "__main__":
    app.run(debug=True)