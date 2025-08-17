import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config

# ------------------ App & DB ------------------
app = Flask(__name__, instance_relative_config=True)
app.config.from_object(Config)

os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ------------------ Models ------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class TechLanguage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    short_desc = db.Column(db.String(300), default='')
    long_desc = db.Column(db.Text, default='')
    price_quote = db.Column(db.Integer, nullable=True)  # in INR or your currency
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tech_id = db.Column(db.Integer, db.ForeignKey('tech_language.id'), nullable=True)
    tech = db.relationship('TechLanguage', backref=db.backref('projects', lazy=True))

class ProjectImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    project = db.relationship('Project', backref=db.backref('images', lazy=True))

class Inquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref=db.backref('inquiries', lazy=True))

    tech_id = db.Column(db.Integer, db.ForeignKey('tech_language.id'), nullable=True)
    tech = db.relationship('TechLanguage')

    details = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------ Login loader ------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------ CLI init ------------------
@app.before_request
def ensure_admin_seed():
    """Seed default admin and default techs once DB exists."""
    db.create_all()
    admin = User.query.filter_by(email=app.config['ADMIN_EMAIL']).first()
    if not admin:
        admin = User(name='Admin', email=app.config['ADMIN_EMAIL'], is_admin=True)
        admin.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin)
        # default techs
        defaults = [
            ('Python', 'APIs, data apps, automation'),
            ('Java', 'Enterprise apps, Android backends'),
            ('Web Development', 'Full-stack websites and PWAs'),
            ('C', 'Embedded, systems programming'),
            ('C++', 'Performance apps, games'),
            ('Other', 'Describe your requirement')
        ]
        for name, desc in defaults:
            if not TechLanguage.query.filter_by(name=name).first():
                db.session.add(TechLanguage(name=name, description=desc))
        db.session.commit()

# ------------------ Auth Routes ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'warning')
            return redirect(url_for('register'))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# ------------------ Client Views ------------------
@app.route('/')
def index():
    techs = TechLanguage.query.filter_by(is_active=True).order_by(TechLanguage.name.asc()).all()
    return render_template('client/index.html', techs=techs)

@app.route('/tech/<int:tech_id>')
def tech_projects(tech_id):
    tech = TechLanguage.query.get_or_404(tech_id)
    if tech.name.lower() == 'other':
        return redirect(url_for('other_request'))
    projects = Project.query.filter_by(tech_id=tech.id).order_by(Project.created_at.desc()).all()
    return render_template('client/projects.html', tech=tech, projects=projects)

@app.route('/other', methods=['GET', 'POST'])
@login_required
def other_request():
    if request.method == 'POST':
        details = request.form.get('details', '').strip()
        if not details:
            flash('Please provide details.', 'warning')
            return redirect(url_for('other_request'))
        inquiry = Inquiry(user=current_user, details=details, tech=None)
        db.session.add(inquiry)
        db.session.commit()
        flash('Thanks! We received your requirement. We will reach out with a quotation.', 'success')
        return redirect(url_for('index'))
    return render_template('client/other_request.html')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------------ Admin Views ------------------
from functools import wraps

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin only.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_projects = Project.query.count()
    total_inquiries = Inquiry.query.count()
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_projects=total_projects,
                           total_inquiries=total_inquiries)

@app.route('/admin/languages', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_languages():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '')
        is_active = bool(request.form.get('is_active'))
        if not name:
            flash('Language name required', 'warning')
        elif TechLanguage.query.filter_by(name=name).first():
            flash('Language already exists', 'warning')
        else:
            db.session.add(TechLanguage(name=name, description=description, is_active=is_active))
            db.session.commit()
            flash('Language added', 'success')
        return redirect(url_for('admin_languages'))
    techs = TechLanguage.query.order_by(TechLanguage.name.asc()).all()
    return render_template('admin/languages.html', techs=techs)

@app.route('/admin/languages/<int:tech_id>/toggle')
@login_required
@admin_required
def toggle_language(tech_id):
    tech = TechLanguage.query.get_or_404(tech_id)
    tech.is_active = not tech.is_active
    db.session.commit()
    flash('Language visibility updated', 'info')
    return redirect(url_for('admin_languages'))

@app.route('/admin/projects')
@login_required
@admin_required
def admin_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    techs = TechLanguage.query.order_by(TechLanguage.name.asc()).all()
    return render_template('admin/projects.html', projects=projects, techs=techs)

@app.route('/admin/projects/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_project_new():
    techs = TechLanguage.query.order_by(TechLanguage.name.asc()).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        short_desc = request.form.get('short_desc', '').strip()
        long_desc = request.form.get('long_desc', '').strip()
        price_quote = request.form.get('price_quote')
        tech_id = request.form.get('tech_id')

        if not title or not tech_id:
            flash('Title and Technology are required', 'warning')
            return redirect(url_for('admin_project_new'))

        project = Project(title=title, short_desc=short_desc, long_desc=long_desc,
                          price_quote=int(price_quote) if price_quote else None,
                          tech_id=int(tech_id))
        db.session.add(project)
        db.session.commit()

        # Handle multiple images
        files = request.files.getlist('images')
        for file in files:
            if file and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                save_name = f"{project.id}_{datetime.utcnow().timestamp()}_{fname}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_name))
                db.session.add(ProjectImage(filename=save_name, project=project))
        db.session.commit()

        flash('Project created', 'success')
        return redirect(url_for('admin_projects'))

    return render_template('admin/project_form.html', techs=techs, project=None)

@app.route('/admin/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    techs = TechLanguage.query.order_by(TechLanguage.name.asc()).all()
    if request.method == 'POST':
        project.title = request.form.get('title', '').strip()
        project.short_desc = request.form.get('short_desc', '').strip()
        project.long_desc = request.form.get('long_desc', '').strip()
        price_quote = request.form.get('price_quote')
        project.price_quote = int(price_quote) if price_quote else None
        project.tech_id = int(request.form.get('tech_id'))

        # Optional: add more images
        files = request.files.getlist('images')
        for file in files:
            if file and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                save_name = f"{project.id}_{datetime.utcnow().timestamp()}_{fname}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_name))
                db.session.add(ProjectImage(filename=save_name, project=project))

        db.session.commit()
        flash('Project updated', 'success')
        return redirect(url_for('admin_projects'))

    return render_template('admin/project_form.html', techs=techs, project=project)

@app.route('/admin/projects/<int:project_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_project_delete(project_id):
    project = Project.query.get_or_404(project_id)
    # delete linked images from disk
    for img in project.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
        except OSError:
            pass
    ProjectImage.query.filter_by(project_id=project.id).delete()
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted', 'info')
    return redirect(url_for('admin_projects'))

@app.route('/admin/images/<int:image_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_image_delete(image_id):
    img = ProjectImage.query.get_or_404(image_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
    except OSError:
        pass
    db.session.delete(img)
    db.session.commit()
    flash('Image removed', 'info')
    return redirect(url_for('admin_projects'))

# ------------------ WhatsApp/Instagram deep links ------------------
@app.context_processor
def inject_social_links():
    return dict(
        WHATSAPP_LINK='https://wa.me/919876543210',
        INSTAGRAM_LINK='https://instagram.com/your_handle'
    )

# ------------------ Run ------------------
if __name__ == '__main__':
    app.run(debug=True)
