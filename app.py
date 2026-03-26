from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import random, string, os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'projectpulse-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///projectpulse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

TEACHER_CODE = 'TEACHER2024'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'zip', 'py', 'txt', 'png', 'jpg', 'jpeg'}

db = SQLAlchemy(app)
os.makedirs('static/uploads', exist_ok=True)

# ── Models ────────────────────────────────────────────────────────────────────

group_members = db.Table('group_members',
    db.Column('user_id',  db.Integer, db.ForeignKey('user.id'),  primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True)
)

class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20),  default='student')
    department    = db.Column(db.String(100), nullable=True)
    is_leader     = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    groups_created = db.relationship('Group', backref='creator', lazy=True, foreign_keys='Group.creator_id')
    tasks_assigned = db.relationship('Task',  backref='assigned_user', lazy=True, foreign_keys='Task.assigned_to')

    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def is_teacher(self):        return self.role == 'teacher'

class Group(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    code         = db.Column(db.String(8),   unique=True, nullable=False)
    creator_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    leader_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    department   = db.Column(db.String(100), nullable=True)
    meeting_link = db.Column(db.String(300), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    members     = db.relationship('User', secondary=group_members, backref=db.backref('groups', lazy=True))
    tasks       = db.relationship('Task',       backref='group', lazy=True, cascade='all, delete-orphan')
    messages    = db.relationship('Message',    backref='group', lazy=True, cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='group', lazy=True, cascade='all, delete-orphan')
    leader      = db.relationship('User', foreign_keys=[leader_id])

class Task(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    group_id    = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    deadline    = db.Column(db.Date, nullable=True)
    status      = db.Column(db.String(20), default='Not Started')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    sender_id  = db.Column(db.Integer, db.ForeignKey('user.id'),  nullable=False)
    content    = db.Column(db.Text, nullable=False)
    file_url   = db.Column(db.String(300), nullable=True)
    file_name  = db.Column(db.String(200), nullable=True)
    room       = db.Column(db.String(20), default='general')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender     = db.relationship('User', foreign_keys=[sender_id])

class Submission(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    group_id     = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    submitter_id = db.Column(db.Integer, db.ForeignKey('user.id'),  nullable=False)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    file_url     = db.Column(db.String(300), nullable=True)
    file_name    = db.Column(db.String(200), nullable=True)
    code_text    = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitter    = db.relationship('User', foreign_keys=[submitter_id])

class Attendance(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('user.id'),  nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    date     = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    present  = db.Column(db.Boolean, default=True)
    user     = db.relationship('User',  foreign_keys=[user_id])
    group    = db.relationship('Group', foreign_keys=[group_id])

# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_group_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not Group.query.filter_by(code=code).first():
            return code

def current_user():
    if 'user_id' in session:
        return db.session.get(User, session['user_id'])
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or not user.is_teacher():
            flash('Teacher access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        email      = request.form.get('email', '').strip()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm_password', '')
        role       = request.form.get('role', 'student')
        department = request.form.get('department', '').strip()
        tcode      = request.form.get('teacher_code', '').strip()

        if not username or not email or not password:
            flash('All fields are required.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        elif role == 'teacher' and tcode != TEACHER_CODE:
            flash('Invalid teacher code.', 'error')
        else:
            user = User(username=username, email=email, role=role, department=department)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id']  = user.id
            session['username'] = user.username
            session['role']     = user.role
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('teacher_dashboard') if user.is_teacher() else url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# ── Student Dashboard ─────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    if user.is_teacher():
        return redirect(url_for('teacher_dashboard'))
    return render_template('dashboard.html', user=user, groups=user.groups)

# ── Teacher Dashboard ─────────────────────────────────────────────────────────

@app.route('/teacher')
@login_required
@teacher_required
def teacher_dashboard():
    user    = current_user()
    groups  = Group.query.all()
    students = User.query.filter_by(role='student').order_by(User.department, User.username).all()
    departments = db.session.query(User.department).filter(User.role=='student', User.department != None, User.department != '').distinct().all()
    departments = [d[0] for d in departments]
    return render_template('teacher_dashboard.html', user=user, groups=groups, students=students, departments=departments)

@app.route('/teacher/assign_leader', methods=['POST'])
@login_required
@teacher_required
def assign_leader():
    group_id  = request.form.get('group_id')
    user_id   = request.form.get('user_id')
    group = Group.query.get_or_404(group_id)
    student   = User.query.get_or_404(user_id)
    if student not in group.members:
        flash('Student is not in this group.', 'error')
    else:
        # Remove old leader flag
        if group.leader_id:
            old = db.session.get(User, group.leader_id)
            if old: old.is_leader = False
        group.leader_id   = student.id
        student.is_leader = True
        db.session.commit()
        flash(f'{student.username} is now the leader of {group.name}.', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def attendance():
    user   = current_user()
    groups = Group.query.all()
    selected_group = None
    records = []
    if request.method == 'POST':
        group_id = request.form.get('group_id')
        selected_group = Group.query.get(group_id)
        date_str = request.form.get('date')
        att_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        for member in selected_group.members:
            present = request.form.get(f'present_{member.id}') == 'on'
            existing = Attendance.query.filter_by(user_id=member.id, group_id=group_id, date=att_date).first()
            if existing:
                existing.present = present
            else:
                db.session.add(Attendance(user_id=member.id, group_id=int(group_id), date=att_date, present=present))
        db.session.commit()
        flash('Attendance saved.', 'success')
    sel_id = request.args.get('group_id')
    if sel_id:
        selected_group = Group.query.get(sel_id)
        records = Attendance.query.filter_by(group_id=sel_id).order_by(Attendance.date.desc()).all()
    return render_template('attendance.html', user=user, groups=groups, selected_group=selected_group, records=records)

@app.route('/teacher/submissions')
@login_required
@teacher_required
def teacher_submissions():
    user = current_user()
    submissions = Submission.query.order_by(Submission.submitted_at.desc()).all()
    return render_template('teacher_submissions.html', user=user, submissions=submissions)

# ── Groups ────────────────────────────────────────────────────────────────────

@app.route('/group/create', methods=['GET', 'POST'])
@login_required
def create_group():
    user = current_user()
    if user.is_teacher():
        return redirect(url_for('teacher_dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        dept = request.form.get('department', '').strip()
        if not name:
            flash('Group name is required.', 'error')
        else:
            group = Group(name=name, code=generate_group_code(), creator_id=user.id, department=dept)
            group.members.append(user)
            db.session.add(group)
            db.session.commit()
            flash(f'Group "{name}" created! Code: {group.code}', 'success')
            return redirect(url_for('group_detail', group_id=group.id))
    return render_template('create_group.html', user=user)

@app.route('/group/join', methods=['GET', 'POST'])
@login_required
def join_group():
    user = current_user()
    if request.method == 'POST':
        code  = request.form.get('code', '').strip().upper()
        group = Group.query.filter_by(code=code).first()
        if not group:
            flash('No group found with that code.', 'error')
        elif user in group.members:
            flash('You are already in this group.', 'error')
        else:
            group.members.append(user)
            db.session.commit()
            flash(f'Joined "{group.name}"!', 'success')
            return redirect(url_for('group_detail', group_id=group.id))
    return render_template('join_group.html', user=user)

@app.route('/group/<int:group_id>')
@login_required
def group_detail(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members and not user.is_teacher():
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    tasks  = Task.query.filter_by(group_id=group_id).order_by(Task.created_at.desc()).all()
    status_counts = {
        'Not Started': sum(1 for t in tasks if t.status == 'Not Started'),
        'In Progress':  sum(1 for t in tasks if t.status == 'In Progress'),
        'Completed':    sum(1 for t in tasks if t.status == 'Completed'),
    }
    is_leader = (group.leader_id == user.id) or user.is_teacher()
    return render_template('group_detail.html', user=user, group=group, tasks=tasks,
                           status_counts=status_counts, is_leader=is_leader)

@app.route('/group/<int:group_id>/set_meeting', methods=['POST'])
@login_required
def set_meeting(group_id):
    group = Group.query.get_or_404(group_id)
    user  = current_user()
    if group.leader_id != user.id and not user.is_teacher():
        flash('Only the leader can set a meeting link.', 'error')
        return redirect(url_for('group_detail', group_id=group_id))
    group.meeting_link = request.form.get('meeting_link', '').strip()
    db.session.commit()
    flash('Meeting link updated.', 'success')
    return redirect(url_for('group_detail', group_id=group_id))

# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.route('/group/<int:group_id>/task/create', methods=['GET', 'POST'])
@login_required
def create_task(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        assigned_to = request.form.get('assigned_to') or None
        deadline_str = request.form.get('deadline', '').strip()
        status      = request.form.get('status', 'Not Started')
        if not title:
            flash('Task title is required.', 'error')
        else:
            deadline = None
            if deadline_str:
                try:    deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                except: flash('Invalid date.', 'error'); return render_template('create_task.html', user=user, group=group)
            db.session.add(Task(title=title, description=description,
                                assigned_to=int(assigned_to) if assigned_to else None,
                                group_id=group_id, deadline=deadline, status=status))
            db.session.commit()
            flash('Task created!', 'success')
            return redirect(url_for('group_detail', group_id=group_id))
    return render_template('create_task.html', user=user, group=group)

@app.route('/task/<int:task_id>/update_status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task  = Task.query.get_or_404(task_id)
    group = Group.query.get(task.group_id)
    user  = current_user()
    if user not in group.members:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    new_status = request.form.get('status')
    if new_status in ['Not Started', 'In Progress', 'Completed']:
        task.status = new_status
        db.session.commit()
    return redirect(url_for('group_detail', group_id=task.group_id))

@app.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    gid  = task.group_id
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted.', 'success')
    return redirect(url_for('group_detail', group_id=gid))

# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route('/group/<int:group_id>/chat')
@login_required
def chat(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members and not user.is_teacher():
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    room = request.args.get('room', 'general')
    is_leader = (group.leader_id == user.id) or user.is_teacher()
    if room == 'leaders' and not is_leader:
        flash('Leaders only chat.', 'error')
        room = 'general'
    messages = Message.query.filter_by(group_id=group_id, room=room).order_by(Message.created_at.asc()).all()
    return render_template('chat.html', user=user, group=group, messages=messages, room=room, is_leader=is_leader)

@app.route('/group/<int:group_id>/chat/send', methods=['POST'])
@login_required
def send_message(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members and not user.is_teacher():
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    room    = request.form.get('room', 'general')
    content = request.form.get('content', '').strip()
    file_url = file_name = None
    f = request.files.get('file')
    if f and f.filename and allowed_file(f.filename):
        filename = secure_filename(f.filename)
        unique   = f'{datetime.utcnow().strftime("%Y%m%d%H%M%S")}_{filename}'
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
        file_url  = f'uploads/{unique}'
        file_name = filename
    if content or file_url:
        db.session.add(Message(group_id=group_id, sender_id=user.id,
                               content=content or '', file_url=file_url,
                               file_name=file_name, room=room))
        db.session.commit()
    return redirect(url_for('chat', group_id=group_id, room=room))

# ── Meeting ───────────────────────────────────────────────────────────────────

@app.route('/group/<int:group_id>/meeting')
@login_required
def meeting(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members and not user.is_teacher():
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('meeting.html', user=user, group=group)

# ── Submissions ───────────────────────────────────────────────────────────────

@app.route('/group/<int:group_id>/submit', methods=['GET', 'POST'])
@login_required
def submit_project(group_id):
    user  = current_user()
    group = Group.query.get_or_404(group_id)
    if user not in group.members:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        code_text   = request.form.get('code_text', '').strip()
        file_url = file_name = None
        f = request.files.get('file')
        if f and f.filename and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            unique   = f'{datetime.utcnow().strftime("%Y%m%d%H%M%S")}_{filename}'
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
            file_url  = f'uploads/{unique}'
            file_name = filename
        if not title:
            flash('Title is required.', 'error')
        else:
            db.session.add(Submission(group_id=group_id, submitter_id=user.id,
                                      title=title, description=description,
                                      file_url=file_url, file_name=file_name,
                                      code_text=code_text))
            db.session.commit()
            flash('Project submitted!', 'success')
            return redirect(url_for('group_detail', group_id=group_id))
    return render_template('submit_project.html', user=user, group=group)

@app.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    flash(f'Group "{group.name}" has been deleted.', 'success')
    return redirect(url_for('teacher_dashboard'))

# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)