"""User module which provides handlers to access and edit users."""
import ast
import base64
import flask
import json
import random

from googleapiclient import errors

from ufo import app
from ufo import db
from ufo import google_directory_service
from ufo import models
from ufo import oauth
from ufo import setup_required

INVITE_CODE_URL_PREFIX = 'https://uproxy.org/connect/'

def _render_user_add(get_all, group_key, user_key):
  credentials = oauth.getSavedCredentials()
  # TODO this should handle the case where we do not have oauth
  if not credentials:
    return flask.render_template('add_user.html',
                                 directory_users=[],
                                 error="OAuth is not set up")

  try:
    directory_service = google_directory_service.GoogleDirectoryService(credentials)

    directory_users = []
    if get_all:
      directory_users = directory_service.GetUsers()
    elif group_key is not None and group_key is not '':
      directory_users = directory_service.GetUsersByGroupKey(group_key)
    elif user_key is not None and user_key is not '':
      directory_users = directory_service.GetUserAsList(user_key)

    return flask.render_template('add_user.html',
                                 directory_users=directory_users)
  except errors.HttpError as error:
    return flask.render_template('add_user.html',
                                 directory_users=[],
                                 error=error)

def _get_random_server_ip():
  proxy_servers = models.ProxyServer.query.all()
  if len(proxy_servers) == 0:
    return None

  index = random.randint(0, len(proxy_servers) - 1)
  return proxy_servers[index].ip_address

def _make_invite_code(user):
  """Create an invite code for the given user.

  The invite code is a format created by the uproxy team.
  Below is an example of an unencoded invite code for a cloud instance:

  {
    "networkName": "Cloud",
    "networkData": "{
      \"host\":\"178.62.123.172\",
      \"user\":\"giver\",
      \"key\":\"base64_key"
    }"
  }

  It includes the host ip (of the proxy server or load balancer) to connect
  the user to, the user username (user's email) to connect with, and
  the credential (private key) necessary to authenticate with the host.

  TODO: Guard against any future breakage when the invite code format
  is changed again.  Possibly adding a test on the uproxy-lib side
  to fail and point to updating this here.

  Args:
    user: A user from the datastore to generate an invite code for.

  Returns:
    invite_code: A base64 encoded dictionary of host, user, and pass which
    correspond to the proxy server/load balancer's ip, the user's email, and
    the user's private key, respectively.  See example above.
  """
  ip = _get_random_server_ip()
  if ip is None:
    return None

  invite_code_data = {
      'networkName': 'Cloud',
      'networkData': {
        'host': ip,
        'user': user.email,
        'pass': user.private_key,
      },
  }
  json_data = json.dumps(invite_code_data)
  invite_code = base64.urlsafe_b64encode(json_data)

  return invite_code

@app.route('/user/')
@setup_required
def user_list():
  users = models.User.query.all()
  user_emails = {}
  for user in users:
    user_emails[user.id] = user.email
  return flask.render_template('user.html',
                               user_payloads=user_emails)

@app.route('/user/add', methods=['GET', 'POST'])
@setup_required
def add_user():
  if flask.request.method == 'GET':
    get_all = flask.request.args.get('get_all')
    group_key = flask.request.args.get('group_key')
    user_key = flask.request.args.get('user_key')
    return _render_user_add(get_all, group_key, user_key)

  manual = flask.request.form.get('manual')
  if manual:
    user_name = flask.request.form.get('user_name')
    user_email = flask.request.form.get('user_email')
    user = models.User()
    user.name = user_name
    user.email = user_email
    user.save()
  else:
    users = flask.request.form.getlist('selected_user')
    for user in users:
      # TODO we should be submitting data in a better format
      u = ast.literal_eval(user)
      user = models.User()
      user.name = u['name']['fullName']
      user.email = u['primaryEmail']
      user.save(commit=False)

    if len(users) > 0:
      db.session.commit()

  return flask.redirect(flask.url_for('user_list'))

@app.route('/user/<user_id>/details')
@setup_required
def user_details(user_id):
  user = models.User.query.get_or_404(user_id)
  invite_code = _make_invite_code(user)
  if invite_code is None:
    return flask.render_template('user_details.html', user=user)
  else:
    invite_url = INVITE_CODE_URL_PREFIX + invite_code
    return flask.render_template('user_details.html', user=user,
                                 invite_url=invite_url)

@app.route('/user/<user_id>/delete', methods=['POST'])
@setup_required
def delete_user(user_id):
  """Delete the user corresponding to the passed in key.

  If we had access to a delete method then we would not use get here.
  """
  user = models.User.query.get_or_404(user_id)
  user.delete()

  return flask.redirect(flask.url_for('user_list'))

@app.route('/user/<user_id>/getNewKeyPair', methods=['POST'])
@setup_required
def user_get_new_key_pair(user_id):
  user = models.User.query.get_or_404(user_id)
  user.regenerate_key_pair()
  user.save()

  return flask.redirect(flask.url_for('user_details', user_id=user_id))

@app.route('/user/<user_id>/toggleRevoked', methods=['POST'])
@setup_required
def user_toggle_revoked(user_id):
  user = models.User.query.get_or_404(user_id)
  user.is_key_revoked = not user.is_key_revoked
  user.save()

  return flask.redirect(flask.url_for('user_details', user_id=user_id))
