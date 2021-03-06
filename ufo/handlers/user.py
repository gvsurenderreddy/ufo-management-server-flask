"""User module which provides handlers to access and edit users."""
import ast
import base64
import json
import random

import flask
from googleapiclient import errors

import ufo
from ufo.database import models
from ufo.handlers import auth
from ufo.services import custom_exceptions
from ufo.services import google_directory_service
from ufo.services import oauth

INVITE_CODE_URL_PREFIX = 'https://uproxy.org/invite#'


def _get_users_to_add(get_all, group_key, user_key):
  """Gets a json object containing the requested users if found.

  If users are found, they are stripped down to only their full name and
  email to avoid leaking unnecessary information. In the case that the
  users are not found, an empty list is used. If an httperror is
  encountered, that error is caught, and the json is still returned
  with the error inserted and an empty list of users.

  Args:
    get_all: A boolean for whether or not to get all users in a domain.
    group_key: A string identifying a group of users and other groups.
    user_key: A string identifying an individual user.

  Returns:
    A json object with 'directory_users' set to a possibly empty list of user
    objects. If there is an error, the 'error' field will be set to its text.
  """
  credentials = oauth.getSavedCredentials()
  # TODO this should handle the case where we do not have oauth
  if not credentials:
    dictionary = {'directory_users': [], 'error': 'OAuth is not set up'}
    json_obj = json.dumps((dictionary))
    return flask.Response(ufo.XSSI_PREFIX + json_obj, headers=ufo.JSON_HEADERS)

  try:
    directory_service = google_directory_service.GoogleDirectoryService(
        credentials)

    directory_users = []
    if get_all:
      directory_users = directory_service.GetUsers()
    elif group_key is not None and group_key is not '':
      directory_users = directory_service.GetUsersByGroupKey(group_key)
    elif user_key is not None and user_key is not '':
      directory_users = directory_service.GetUserAsList(user_key)

    users_to_output = []
    for directory_user in directory_users:
      user_for_display = {
          'name': directory_user['name']['fullName'],
          'email': directory_user['primaryEmail']
      }
      users_to_output.append(user_for_display)

    json_obj = json.dumps(({'directory_users': users_to_output}))
    return flask.Response(ufo.XSSI_PREFIX + json_obj, headers=ufo.JSON_HEADERS)

  except errors.HttpError as error:
    json_obj = json.dumps(({'directory_users': [], 'error': str(error)}))
    return flask.Response(ufo.XSSI_PREFIX + json_obj, headers=ufo.JSON_HEADERS)

def _get_random_server_ip():
  """Gets the ip address of a random proxy server of those in the db.

  Returns:
    A randomly selected proxy server's ip address as a string.
  """
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
      \"user\":\"getter\",
      \"key\":\"base64_key"
    }"
  }

  It includes the host ip (of the proxy server or load balancer) to connect
  the user to, the user (getter)) to connect with, and
  the credential (private key) necessary to authenticate with the host.

  TODO: Guard against any future breakage when the invite code format
  is changed again.  Possibly adding a test on the uproxy-lib side
  to fail and point to updating this here.

  Args:
    user: A user from the datastore to generate an invite code for.

  Returns:
    invite_code: A base64 encoded dictionary of network name and data, which
    includes the host, user, and key corresponding to the proxy server/load
    balancer's ip, the user account (getter), and the user's private key,
    respectively.  See example above.
  """
  ip = _get_random_server_ip()
  if ip is None:
    return None

  invite_code_data = {
      'networkName': 'Cloud',
      'networkData': {
        'host': ip,
        'user': 'getter',
        'key': base64.urlsafe_b64encode(user.private_key),
      },
  }
  json_data = json.dumps(invite_code_data)
  invite_code = base64.urlsafe_b64encode(json_data)

  return invite_code

@ufo.app.route('/user/')
@ufo.setup_required
@auth.login_required
def user_list():
  """Retrieves a list of the users currently in the db.

  Returns:
    A json object with 'items' set to the list of users in the db.
  """
  users_json = json.dumps(({'items': models.User.get_items_as_list_of_dict()}))
  return flask.Response(ufo.XSSI_PREFIX + users_json, headers=ufo.JSON_HEADERS)

@ufo.app.route('/user/add', methods=['GET', 'POST'])
@ufo.setup_required
@auth.login_required
def add_user():
  """Gets the requested users on get and stores new user(s) on post.

  This one handler does get and post for add user. The get method is handled
  by _render_user_add with the parameters for get_all, group_key, and user_key
  each passed along. The post method is handled here by inserting the new user
  or users into the database and redirecting to the user_list page.

  Returns:
    A list of the requested users for a get or redirects to the user_list page
    after inserting users for a post.
  """
  if flask.request.method == 'GET':
    get_all = flask.request.args.get('get_all')
    group_key = flask.request.args.get('group_key')
    user_key = flask.request.args.get('user_key')
    return _get_users_to_add(get_all, group_key, user_key)

  manual = flask.request.form.get('manual')
  users_list = json.loads(flask.request.form.get('users'))
  config = ufo.get_user_config()
  for submitted_user in users_list:
    db_user = models.User()
    db_user.name = submitted_user['name']
    db_user.email = submitted_user['email']
    db_user.domain = config.domain if manual is None else None
    # Save on each user so that we can let the database check if the
    # uniqueness constraint is fulfilled.  i.e don't batch this because
    # if one user is added more than once then the whole session will fail.
    try:
      db_user.save()
    except custom_exceptions.UnableToSaveToDB as e:
      flask.abort(e.code, e.message)

  return user_list()

@ufo.app.route('/user/delete', methods=['POST'])
@ufo.setup_required
@auth.login_required
def delete_user():
  """Deletes the user corresponding to the passed in user_id from the db.

  If we had access to a delete method then we would not use get here.
  If the user is not found, this produces a 404 error which redirects to the
  error handler.

  Returns:
    A redirect to the user_list page after deleting the given user.
  """
  user_id = json.loads(flask.request.form.get('user_id'))
  user = models.User.query.get_or_404(user_id)
  user.delete()

  return user_list()

@ufo.app.route('/user/getNewKeyPair', methods=['POST'])
@ufo.setup_required
@auth.login_required
def user_get_new_key_pair():
  """Rotates the key pair (public and private keys) for the given user.

  If the user is not found, this produces a 404 error which redirects to the
  error handler.

  Returns:
    A redirect to the user_details page after rotating the user's keys.
  """
  user_id = json.loads(flask.request.form.get('user_id'))
  user = models.User.query.get_or_404(user_id)
  user.regenerate_key_pair()
  user.save()

  return flask.redirect(flask.url_for('user_list'))

@ufo.app.route('/user/getInviteCode', methods=['GET'])
@ufo.setup_required
@auth.login_required
def user_get_invite_code():
  """Get an invite code for the given user.

  If the user is not found, this produces a 404 error which redirects to the
  error handler.

  Returns:
    A json object with 'invite_code' set to the invite code string.
  """
  user_id = json.loads(flask.request.args.get('user_id'))
  user = models.User.query.get_or_404(user_id)
  invite_code = _make_invite_code(user)
  code_json = None
  if invite_code is None:
    code_json = json.dumps(({'invite_code': False}))
  else:
    invite_url = INVITE_CODE_URL_PREFIX + invite_code
    code_json = json.dumps(({'invite_code': invite_url}))
  return flask.Response(ufo.XSSI_PREFIX + code_json, headers=ufo.JSON_HEADERS)

@ufo.app.route('/user/toggleRevoked', methods=['POST'])
@ufo.setup_required
@auth.login_required
def user_toggle_revoked():
  """Toggles whether the given user's access is revoked or not.

  If the user is not found, this produces a 404 error which redirects to the
  error handler.

  Returns:
    A redirect to the user_details page after flipping is_key_revoked.
  """
  user_id = json.loads(flask.request.form.get('user_id'))
  user = models.User.query.get_or_404(user_id)
  user.is_key_revoked = not user.is_key_revoked
  user.did_cron_revoke = False
  user.save()

  return flask.redirect(flask.url_for('user_list'))
