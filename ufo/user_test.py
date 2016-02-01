"""Test user module functionality."""
from mock import MagicMock
from mock import patch

import base64
import flask
from googleapiclient import errors
import json
import unittest
from werkzeug.datastructures import MultiDict
from werkzeug.datastructures import ImmutableMultiDict

from . import app
import base_test
from . import db
# I practically have to shorten this name so every single line doesn't go
# over. If someone can't understand, they can use ctrl+f to look it up here.
import google_directory_service as gds
import models
import oauth
import user

FAKE_EMAILS_AND_NAMES = [
  {'email': 'foo@aol.com', 'name': 'joe'},
  {'email': 'bar@yahoo.com', 'name': 'bob'},
  {'email': 'baz@gmail.com', 'name': 'mark'}
]
FAKE_DIRECTORY_USER_ARRAY = []
for fake_email_and_name in FAKE_EMAILS_AND_NAMES:
  fake_directory_user = {}
  fake_directory_user['primaryEmail'] = fake_email_and_name['email']
  fake_directory_user['name'] = {}
  fake_directory_user['name']['fullName'] = fake_email_and_name['name']
  fake_directory_user['email'] = fake_email_and_name['email']
  fake_directory_user['role'] = 'MEMBER'
  fake_directory_user['type'] = 'USER'
  FAKE_DIRECTORY_USER_ARRAY.append(fake_directory_user)

FAKE_CREDENTIAL = 'Look at me. I am a credential!'

FAKE_MODEL_USER = MagicMock(email=FAKE_EMAILS_AND_NAMES[0]['email'],
                            name=FAKE_EMAILS_AND_NAMES[0]['name'],
                            private_key='private key foo',
                            public_key='public key bar',
                            is_key_revoked=False)
class UserTest(base_test.BaseTest):
  """Test user class functionality."""

  def setUp(self):
    """Setup test app on which to call handlers and db to query."""
    super(UserTest, self).setUp()
    super(UserTest, self).setup_config()

  def testListUsersHandler(self):
    """Test the list user handler displays users from the database."""
    users = []
    for fake_email_and_name in FAKE_EMAILS_AND_NAMES:
      user = models.User(email=fake_email_and_name['email'],
                         name=fake_email_and_name['name'])
      user.save()
      users.append(user)

    resp = self.client.get(flask.url_for('user_list'))
    user_list_output = resp.data

    self.assertTrue('Add Users' in user_list_output)
    click_user_string = 'Click a user below to view more details.'
    self.assertTrue(click_user_string in user_list_output)

    for user in users:
      self.assertTrue(user.email in user_list_output)
      details_link = flask.url_for('user_details', user_id=user.id)
      self.assertTrue(details_link in user_list_output)

  @patch.object(user, '_RenderUserAdd')
  def testAddUsersGetHandler(self, mock_render):
    """Test the add users get handler returns _RenderUserAdd's result."""
    return_text = '<html>something here </html>'
    mock_render.return_value = return_text
    resp = self.client.get(flask.url_for('add_user'))

    self.assertEquals(resp.data, return_text)

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  def testAddUsersGetNoCredentials(self, mock_get_saved_credentials,
                                  mock_render_template):
    """Test add user get should display an error when oauth isn't set."""
    mock_get_saved_credentials.return_value = None
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user'))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals([], kwargs['directory_users'])
    self.assertIsNotNone(kwargs['error'])

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  @patch.object(gds.GoogleDirectoryService, '__init__')
  def testAddUsersGetNoParam(self, mock_gds, mock_get_saved_credentials,
                            mock_render_template):
    """Test add user get should display no users on initial get."""
    mock_get_saved_credentials.return_value = FAKE_CREDENTIAL
    mock_gds.return_value = None
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user'))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals([], kwargs['directory_users'])

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  @patch.object(gds.GoogleDirectoryService, 'GetUsersByGroupKey')
  @patch.object(gds.GoogleDirectoryService, '__init__')
  def testAddUsersGetWithGroup(self, mock_gds, mock_get_by_key,
                              mock_get_saved_credentials,
                              mock_render_template):
    """Test add user get should display users from a given group."""
    mock_get_saved_credentials.return_value = FAKE_CREDENTIAL
    mock_gds.return_value = None
    # Email address could refer to group or user
    group_key = 'foo@bar.mybusiness.com'
    mock_get_by_key.return_value = FAKE_DIRECTORY_USER_ARRAY
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user', group_key=group_key))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals(FAKE_DIRECTORY_USER_ARRAY, kwargs['directory_users'])

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  @patch.object(gds.GoogleDirectoryService, 'GetUserAsList')
  @patch.object(gds.GoogleDirectoryService, '__init__')
  def testAddUsersGetWithUser(self, mock_gds, mock_get_user,
                             mock_get_saved_credentials,
                             mock_render_template):
    """Test add user get should display a given user as requested."""
    mock_get_saved_credentials.return_value = FAKE_CREDENTIAL
    mock_gds.return_value = None
    # Email address could refer to group or user
    user_key = 'foo@bar.mybusiness.com'
    mock_get_user.return_value = FAKE_DIRECTORY_USER_ARRAY
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user', user_key=user_key))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals(FAKE_DIRECTORY_USER_ARRAY, kwargs['directory_users'])

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  @patch.object(gds.GoogleDirectoryService, 'GetUsers')
  @patch.object(gds.GoogleDirectoryService, '__init__')
  def testAddUsersGetWithAll(self, mock_gds, mock_get_users,
                            mock_get_saved_credentials,
                            mock_render_template):
    """Test add user get should display all users in a domain."""
    mock_get_saved_credentials.return_value = FAKE_CREDENTIAL
    mock_gds.return_value = None
    mock_get_users.return_value = FAKE_DIRECTORY_USER_ARRAY
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user', get_all=True))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals(FAKE_DIRECTORY_USER_ARRAY, kwargs['directory_users'])

  @patch('flask.render_template')
  @patch.object(oauth, 'getSavedCredentials')
  @patch.object(gds.GoogleDirectoryService, '__init__')
  def testAddUsersGetWithError(self, mock_gds, mock_get_saved_credentials,
                              mock_render_template):
    """Test add users get fails gracefully when a resource isn't found.

    We need to catch errors from the google directory service module since we
    have not yet implemented robust error handling. Here I'm simulating an
    exception in the directory service and asserting that we catch it and still
    render the add_user page along with the error rather than barfing
    completely.
    """
    mock_get_saved_credentials.return_value = FAKE_CREDENTIAL
    fake_status = '404'
    fake_response = MagicMock(status=fake_status)
    fake_content = b'some error content'
    fake_error = errors.HttpError(fake_response, fake_content)
    mock_gds.side_effect = fake_error
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('add_user'))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('add_user.html', args[0])
    self.assertEquals([], kwargs['directory_users'])
    self.assertEquals(fake_error, kwargs['error'])

  def testAddUsersPostHandler(self):
    """Test the add users post handler calls to insert the specified users."""
    mock_users = []
    data = MultiDict()
    for fake_email_and_name in FAKE_EMAILS_AND_NAMES:
      mock_user = {}
      mock_user['primaryEmail'] = fake_email_and_name['email']
      mock_user['name'] = {}
      mock_user['name']['fullName'] = fake_email_and_name['name']
      mock_users.append(mock_user)
      data.add('selected_user', json.dumps(mock_user))

    data = ImmutableMultiDict(data)

    response = self.client.post(flask.url_for('add_user'), data=data,
                                follow_redirects=False)

    users_count = models.User.query.count()
    self.assertEquals(len(FAKE_EMAILS_AND_NAMES), users_count)

    users_in_db = models.User.query.all()
    self.assertEquals(len(FAKE_EMAILS_AND_NAMES), len(users_in_db))

    for fake_email_and_name in FAKE_EMAILS_AND_NAMES:
      query = models.User.query.filter_by(email=fake_email_and_name['email'])
      user_in_db = query.one_or_none()
      self.assertEqual(fake_email_and_name['name'], user_in_db.name)

    self.assert_redirects(response, flask.url_for('user_list'))

  def testAddUsersPostManualHandler(self):
    """Test add users manually calls to insert the specified user."""
    data = {}
    data['manual'] = True
    data['user_email'] = FAKE_EMAILS_AND_NAMES[0]['email']
    data['user_name'] = FAKE_EMAILS_AND_NAMES[0]['name']

    response = self.client.post(flask.url_for('add_user'), data=data,
                                follow_redirects=False)

    query = models.User.query.filter_by(email=FAKE_EMAILS_AND_NAMES[0]['email'])
    user_in_db = query.one_or_none()
    self.assertIsNotNone(user_in_db)
    self.assertEqual(FAKE_EMAILS_AND_NAMES[0]['name'], user_in_db.name)

    self.assert_redirects(response, flask.url_for('user_list'))

  @patch('flask.render_template')
  def testUserDetailsGet(self, mock_render_template):
    """Test the user details handler calls to render a user's information."""
    user = self._CreateAndSaveFakeUser()
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('user_details', user_id=user.id))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('user_details.html', args[0])
    self.assertEquals(user, kwargs['user'])
    self.assertIsNone(kwargs['invite_code'])

  @patch('flask.render_template')
  def testUserDetailsGetWithInvite(self, mock_render_template):
    """Test the user details handler renders a valid invite code."""
    fake_ip = '0.1.2.3'
    proxy_server = models.ProxyServer(ip_address=fake_ip)
    proxy_server.save()
    user = self._CreateAndSaveFakeUser()
    mock_render_template.return_value = ''

    response = self.client.get(flask.url_for('user_details', user_id=user.id))

    args, kwargs = mock_render_template.call_args
    self.assertEquals('user_details.html', args[0])
    self.assertEquals(user, kwargs['user'])
    self.assertIsNotNone(kwargs['invite_code'])

    invite_code_json = base64.urlsafe_b64decode(kwargs['invite_code'])
    invite_code = json.loads(invite_code_json)

    self.assertEquals('Cloud', invite_code['networkName'])
    self.assertEquals(fake_ip, invite_code['networkData']['host'])
    self.assertEquals(user.email,
                      invite_code['networkData']['user'])
    self.assertEquals(user.private_key,
                      invite_code['networkData']['pass'])

  def testDeleteUserPostHandler(self):
    """Test the delete user handler calls to delete the specified user."""
    user = self._CreateAndSaveFakeUser()
    user_id = user.id

    response = self.client.post(flask.url_for('delete_user', user_id=user_id),
                                follow_redirects=False)

    user = models.User.query.get(user_id)
    self.assertIsNone(user)
    self.assert_redirects(response, flask.url_for('user_list'))

  def testUserGetNewKeyPairHandler(self):
    """Test get new key pair handler regenerates a key pair for the user."""
    user = self._CreateAndSaveFakeUser()
    user_id = user.id
    user_private_key = user.private_key

    response = self.client.post(flask.url_for('user_get_new_key_pair',
                                              user_id=user_id),
                                follow_redirects=False)

    self.assertNotEqual(user_private_key, user.private_key)

    self.assert_redirects(response, flask.url_for('user_details',
                                                  user_id=user_id))

  def testUserToggleRevokedHandler(self):
    """Test toggle revoked handler changes the revoked status for a user."""
    user = self._CreateAndSaveFakeUser()
    initial_revoked_status = user.is_key_revoked

    response = self.client.post(flask.url_for('user_toggle_revoked',
                                              user_id=user.id),
                                follow_redirects=False)

    self.assertEquals(not initial_revoked_status, user.is_key_revoked)
    self.assert_redirects(response, flask.url_for('user_details',
                                                  user_id=user.id))

  def _CreateAndSaveFakeUser(self):
    """Create a fake user object, and save it into db."""
    user = models.User(email=FAKE_EMAILS_AND_NAMES[0]['email'],
                       name=FAKE_EMAILS_AND_NAMES[0]['name'])
    return user.save()


if __name__ == '__main__':
  unittest.main()