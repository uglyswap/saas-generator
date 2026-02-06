"""Authentication blueprint - login, register, logout, first-run setup."""
import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User
from app.utils.security import hash_password, check_password
from app.utils.validators import validate_username, validate_email, validate_password

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.before_app_request
def require_setup():
    """Redirect to setup page if no users exist yet."""
    if request.endpoint and request.endpoint.startswith('static'):
        return None
    if User.query.count() == 0:
        allowed = ('auth.setup', 'auth.setup_post', 'static')
        if request.endpoint not in allowed:
            return redirect(url_for('auth.setup'))
    return None


@auth_bp.route('/setup', methods=['GET'])
def setup():
    """First-run setup page - create admin account."""
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))
    return render_template('auth/setup.html')


@auth_bp.route('/setup', methods=['POST'])
def setup_post():
    """Handle first-run admin account creation."""
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    password_confirm = request.form.get('password_confirm', '')

    # Validation
    ok, err = validate_username(username)
    if not ok:
        flash(err, 'error')
        return render_template('auth/setup.html'), 400

    ok, err = validate_email(email)
    if not ok:
        flash(err, 'error')
        return render_template('auth/setup.html'), 400

    ok, err = validate_password(password)
    if not ok:
        flash(err, 'error')
        return render_template('auth/setup.html'), 400

    if password != password_confirm:
        flash('Les mots de passe ne correspondent pas', 'error')
        return render_template('auth/setup.html'), 400

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_admin=True,
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)
    logger.info('Admin account created: %s', username)
    flash('Compte administrateur cree avec succes !', 'success')
    return redirect(url_for('views.index'))


@auth_bp.route('/login', methods=['GET'])
def login():
    """Login page."""
    if current_user.is_authenticated:
        return redirect(url_for('views.index'))
    return render_template('auth/login.html')


@auth_bp.route('/login', methods=['POST'])
def login_post():
    """Handle login."""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    remember = request.form.get('remember') == 'on'

    user = User.query.filter(
        db.or_(User.username == username, User.email == username)
    ).first()

    if not user or not check_password(password, user.password_hash):
        flash('Identifiants incorrects', 'error')
        return render_template('auth/login.html'), 401

    login_user(user, remember=remember)
    logger.info('User logged in: %s', user.username)

    next_page = request.args.get('next')
    if next_page and next_page.startswith('/'):
        return redirect(next_page)
    return redirect(url_for('views.index'))


@auth_bp.route('/register', methods=['GET'])
def register():
    """Registration page."""
    if current_user.is_authenticated:
        return redirect(url_for('views.index'))
    return render_template('auth/register.html')


@auth_bp.route('/register', methods=['POST'])
def register_post():
    """Handle registration."""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    password_confirm = request.form.get('password_confirm', '')

    ok, err = validate_username(username)
    if not ok:
        flash(err, 'error')
        return render_template('auth/register.html'), 400

    ok, err = validate_email(email)
    if not ok:
        flash(err, 'error')
        return render_template('auth/register.html'), 400

    ok, err = validate_password(password)
    if not ok:
        flash(err, 'error')
        return render_template('auth/register.html'), 400

    if password != password_confirm:
        flash('Les mots de passe ne correspondent pas', 'error')
        return render_template('auth/register.html'), 400

    if User.query.filter_by(username=username).first():
        flash("Ce nom d'utilisateur est deja pris", 'error')
        return render_template('auth/register.html'), 409

    if User.query.filter_by(email=email).first():
        flash('Cet email est deja utilise', 'error')
        return render_template('auth/register.html'), 409

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)
    logger.info('User registered: %s', username)
    flash('Compte cree avec succes !', 'success')
    return redirect(url_for('views.index'))


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out current user."""
    logger.info('User logged out: %s', current_user.username)
    logout_user()
    flash('Deconnexion reussie', 'success')
    return redirect(url_for('auth.login'))
