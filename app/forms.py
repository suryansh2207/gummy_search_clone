from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, EmailField
from wtforms.validators import DataRequired, Email, Length

class ProfileForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=80)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('New Password')
    submit = SubmitField('Update Profile')